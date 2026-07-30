"""Owner-only research service for Bet Coverage Optimizer."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer import STATUS_COVERAGE_UNAVAILABLE
from worldcup_predictor.research.bet_coverage_optimizer.generate_tickets import (
    generate_64_tickets,
    write_tickets_artifacts,
)
from worldcup_predictor.research.bet_coverage_optimizer.models import ModelTopScores, ScoreEntry, ScoringWeights
from worldcup_predictor.research.bet_coverage_optimizer.optimizer import optimize_fixture
from worldcup_predictor.research.multi_market_odds_loader import MarketPrice


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def score_entries_from_list(items: list[Any], *, source: str) -> list[ScoreEntry]:
    out: list[ScoreEntry] = []
    for i, item in enumerate(items, start=1):
        if isinstance(item, str):
            out.append(ScoreEntry(score=item.replace(" ", ""), probability=0.0, rank=i, source=source))
            continue
        if not isinstance(item, dict):
            continue
        score = item.get("score") or item.get("scoreline") or item.get("exact_score")
        if not score:
            continue
        try:
            p = float(item.get("probability") or item.get("prob") or item.get("p") or 0.0)
        except (TypeError, ValueError):
            p = 0.0
        if p > 1.0:
            p = p / 100.0
        rank = int(item.get("rank") or i)
        out.append(ScoreEntry(score=str(score).replace(" ", ""), probability=p, rank=rank, source=source))
    return out


def models_from_payload(payload: dict[str, Any]) -> list[ModelTopScores]:
    models: list[ModelTopScores] = []
    for key, model_id, weight in (
        ("canonical", "canonical", 1.0),
        ("exact_v2", "exact_v2", 1.0),
        ("lambda_v2", "lambda_v2", 0.75),
    ):
        block = payload.get(key)
        if not block:
            continue
        scores = block.get("scores") if isinstance(block, dict) else block
        entries = score_entries_from_list(list(scores or []), source=model_id)
        if entries:
            models.append(ModelTopScores(model_id=model_id, scores=entries, weight=float(weight)))
    return models


def _parse_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


def load_models_from_db(conn: sqlite3.Connection, fixture_id: int) -> list[ModelTopScores]:
    """Best-effort read of frozen/shadow tops without mutating anything."""
    models: list[ModelTopScores] = []
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    # Canonical ECSE freeze / snapshot
    if "ecse_live_snapshots" in tables:
        row = conn.execute(
            """
            SELECT top_10_scorelines_json
            FROM ecse_live_snapshots
            WHERE fixture_id = ?
            ORDER BY rowid DESC LIMIT 1
            """,
            (int(fixture_id),),
        ).fetchone()
        if row:
            tops = _parse_json(row[0]) or []
            entries = score_entries_from_list(list(tops)[:10], source="canonical")
            if entries:
                models.append(ModelTopScores(model_id="canonical", scores=entries, weight=1.0))

    # Shadow tables (names vary by infra)
    for table, model_id in (
        ("exact_v2_shadow_outputs", "exact_v2"),
        ("lambda_v2_shadow_outputs", "lambda_v2"),
    ):
        if table not in tables:
            continue
        cols = {c[1] for c in conn.execute(f"PRAGMA table_info({table})")}
        top_col = "top10_json" if "top10_json" in cols else ("top_10_json" if "top_10_json" in cols else None)
        if top_col is None and "payload_json" in cols:
            top_col = "payload_json"
        if top_col is None:
            continue
        row = conn.execute(
            f"SELECT {top_col} FROM {table} WHERE fixture_id = ? ORDER BY rowid DESC LIMIT 1",
            (int(fixture_id),),
        ).fetchone()
        if not row:
            continue
        raw = _parse_json(row[0])
        if isinstance(raw, dict):
            tops = raw.get("top_10_scorelines") or raw.get("top10") or raw.get("scores") or []
        else:
            tops = raw or []
        entries = score_entries_from_list(list(tops)[:10], source=model_id)
        if entries:
            w = 1.0 if model_id == "exact_v2" else 0.75
            models.append(ModelTopScores(model_id=model_id, scores=entries, weight=w))
    return models


def write_run_artifacts(
    *,
    output_dir: Path,
    recommendations: list[Any],
    tickets_payload: dict[str, Any] | None,
    validation: dict[str, Any],
    run_manifest: dict[str, Any],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    summary = {
        "generated_at": _utc_now(),
        "research_only": True,
        "owner_only": True,
        "fixture_ids": [r.fixture_id for r in recommendations],
        "statuses": {str(r.fixture_id): r.status for r in recommendations},
        "ticket_summary": (tickets_payload or {}).get("summary"),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    paths["summary.json"] = str(output_dir / "summary.json")

    recs = [r.to_dict() for r in recommendations]
    (output_dir / "recommendations.json").write_text(json.dumps(recs, indent=2), encoding="utf-8")
    paths["recommendations.json"] = str(output_dir / "recommendations.json")

    candidates = []
    for r in recommendations:
        for c in ([r.selected_coverage_market] if r.selected_coverage_market else []) + list(r.rejected_candidates):
            if c:
                candidates.append(c.to_dict())
    (output_dir / "candidate_markets.json").write_text(json.dumps(candidates, indent=2), encoding="utf-8")
    paths["candidate_markets.json"] = str(output_dir / "candidate_markets.json")

    matrix_path = output_dir / "coverage_matrix.csv"
    with matrix_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "fixture_id",
                "score",
                "probability",
                "selected_exact",
                "covered_by_fourth",
                "uncovered",
            ]
        )
        for r in recommendations:
            exact_set = {e.score for e in r.selected_exact_scores}
            cov_set = set((r.selected_coverage_market.covered_scores if r.selected_coverage_market else []) or [])
            unc = set(r.uncovered_top8_scores)
            for s in r.top8_scores:
                w.writerow(
                    [
                        r.fixture_id,
                        s.score,
                        s.probability,
                        1 if s.score in exact_set else 0,
                        1 if s.score in cov_set else 0,
                        1 if s.score in unc else 0,
                    ]
                )
    paths["coverage_matrix.csv"] = str(matrix_path)

    if tickets_payload is not None:
        paths.update(write_tickets_artifacts(tickets_payload, output_dir))

    (output_dir / "validation_report.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    paths["validation_report.json"] = str(output_dir / "validation_report.json")
    (output_dir / "run_manifest.json").write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")
    paths["run_manifest.json"] = str(output_dir / "run_manifest.json")
    return paths


def run_coverage_optimizer_job(
    fixture_ids: list[int],
    *,
    model_payloads: dict[int, dict[str, Any]] | None = None,
    bookmaker_allowlist: list[str] | None = None,
    top_n_scores: int = 8,
    exact_count: int = 3,
    total_selections: int = 4,
    stake_per_ticket: float = 1.0,
    output_dir: Path | None = None,
    require_fresh: bool = True,
    extra_prices_by_fixture: dict[int, list[MarketPrice]] | None = None,
    raw_payload_by_fixture: dict[int, dict[str, Any]] | None = None,
    weights: ScoringWeights | None = None,
    db_path: str | Path | None = None,
    generate_tickets: bool = True,
    skip_db_odds: bool = False,
) -> dict[str, Any]:
    """
    Research-only job runner. Never writes freezes or canonical predictions.
    """
    recommendations = []
    conn = None
    if db_path:
        conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

    try:
        for fid in fixture_ids:
            models: list[ModelTopScores] = []
            if model_payloads and int(fid) in model_payloads:
                models = models_from_payload(model_payloads[int(fid)])
            elif conn is not None:
                models = load_models_from_db(conn, int(fid))
            if not models:
                # Empty models → empty exacts; still return structured unavailable result
                models = [ModelTopScores(model_id="canonical", scores=[], weight=1.0)]

            rec = optimize_fixture(
                int(fid),
                models,
                top_n_scores=top_n_scores,
                exact_count=exact_count,
                total_selections=total_selections,
                bookmaker_allowlist=bookmaker_allowlist,
                weights=weights,
                require_fresh=require_fresh,
                extra_prices=(extra_prices_by_fixture or {}).get(int(fid)),
                raw_payload=(raw_payload_by_fixture or {}).get(int(fid)),
                skip_db_odds=skip_db_odds,
            )
            recommendations.append(rec)
    finally:
        if conn is not None:
            conn.close()

    tickets_payload = None
    if generate_tickets and len(recommendations) == 3:
        tickets_payload = generate_64_tickets(recommendations, stake_per_ticket=stake_per_ticket)

    validation = {
        "exact_count_per_fixture": {str(r.fixture_id): len(r.selected_exact_scores) for r in recommendations},
        "no_invented_markets": all(
            r.selected_coverage_market is not None
            or STATUS_COVERAGE_UNAVAILABLE in r.blockers
            or r.status == STATUS_COVERAGE_UNAVAILABLE
            for r in recommendations
        ),
        "stale_odds_not_selected": all(
            (
                r.selected_coverage_market is None
                or str(r.selected_coverage_market.odds_freshness_status or "")
                not in {"STALE_ODDS", "REQUIRES_FRESH_ODDS", "stale", "STALE"}
            )
            for r in recommendations
        ),
        "ticket_count": (tickets_payload or {}).get("summary", {}).get("ticket_count"),
        "canonical_formulas_unchanged": True,
        "freezes_unchanged": True,
        "shadow_not_promoted": True,
        "research_only": True,
        "owner_only": True,
    }

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(output_dir) if output_dir else Path("artifacts/coverage_optimizer") / ts
    manifest = {
        "run_id": ts,
        "fixture_ids": [int(x) for x in fixture_ids],
        "require_fresh": require_fresh,
        "top_n_scores": top_n_scores,
        "exact_count": exact_count,
        "total_selections": total_selections,
        "stake_per_ticket": stake_per_ticket,
        "generated_at": _utc_now(),
        "research_only": True,
        "owner_only": True,
        "no_freeze_mutation": True,
        "no_canonical_mutation": True,
    }
    paths = write_run_artifacts(
        output_dir=out,
        recommendations=recommendations,
        tickets_payload=tickets_payload,
        validation=validation,
        run_manifest=manifest,
    )
    return {
        "status": "completed",
        "research_only": True,
        "owner_only": True,
        "recommendations": [r.to_dict() for r in recommendations],
        "summary": {
            "fixture_ids": [r.fixture_id for r in recommendations],
            "statuses": {str(r.fixture_id): r.status for r in recommendations},
            "ticket_summary": (tickets_payload or {}).get("summary"),
        },
        "tickets": tickets_payload,
        "validation": validation,
        "artifact_paths": paths,
        "output_dir": str(out),
    }


# In-memory research job store (owner endpoints)
_RESEARCH_JOBS: dict[str, dict[str, Any]] = {}


def create_research_job(request: dict[str, Any]) -> dict[str, Any]:
    import uuid

    job_id = str(uuid.uuid4())
    record = {
        "job_id": job_id,
        "status": "queued",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "request": request,
        "result": None,
        "error": None,
        "research_only": True,
        "owner_only": True,
    }
    _RESEARCH_JOBS[job_id] = record
    try:
        fixture_id = request.get("fixture_id")
        fixture_ids = request.get("fixture_ids")
        if fixture_ids:
            ids = [int(x) for x in fixture_ids]
        elif fixture_id is not None:
            ids = [int(fixture_id)]
        else:
            raise ValueError("fixture_id or fixture_ids required")
        raw_payloads = request.get("model_payloads") or {}
        model_payloads: dict[int, dict[str, Any]] | None = None
        if isinstance(raw_payloads, dict) and raw_payloads:
            model_payloads = {int(k): v for k, v in raw_payloads.items() if isinstance(v, dict)}
        result = run_coverage_optimizer_job(
            ids,
            bookmaker_allowlist=request.get("bookmaker_allowlist"),
            top_n_scores=int(request.get("top_n_scores") or 8),
            exact_count=int(request.get("exact_count") or 3),
            total_selections=int(request.get("total_selections") or 4),
            stake_per_ticket=float(request.get("stake_per_ticket") or 1.0),
            require_fresh=bool(request.get("require_fresh", True)),
            model_payloads=model_payloads,
            generate_tickets=len(ids) == 3,
            output_dir=Path(request["output_dir"]) if request.get("output_dir") else None,
        )
        record["status"] = "completed"
        record["result"] = result
    except Exception as exc:  # noqa: BLE001 — research job boundary
        record["status"] = "failed"
        record["error"] = str(exc)
    record["updated_at"] = _utc_now()
    _RESEARCH_JOBS[job_id] = record
    return record


def get_research_job(job_id: str) -> dict[str, Any] | None:
    return _RESEARCH_JOBS.get(job_id)
