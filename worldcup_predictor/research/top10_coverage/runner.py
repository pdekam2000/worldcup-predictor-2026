"""Batch runner — read-only coverage analysis."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_match_display import resolve_registry_fixture_id
from worldcup_predictor.research.ecse_rerank.features import (
    extract_wde_markets,
    is_knockout_fixture,
    odds_freshness_meta,
    result_context,
)
from worldcup_predictor.research.top10_coverage.coverage import (
    build_coverage_record,
    load_distribution_ranks,
    load_snapshot_top10,
)
from worldcup_predictor.research.top10_coverage.diagnosis import classify_root_cause, diagnose_top5_miss, miss_due_to_ranking_or_absence
from worldcup_predictor.research.top10_coverage.evaluator import aggregate_summary, can_89pct_from_candidates
from worldcup_predictor.research.top10_coverage.features import PHASE, actual_outcome
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly

SHADOW_ONLY = True


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    return row is not None


def _load_optimizer_hits(root: Path) -> dict[int, bool]:
    path = root / "artifacts" / "top3_endresult_optimizer_1_results.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[int, bool] = {}
    for m in data.get("matches") or []:
        if not m.get("actual_90min"):
            continue
        fid = int(m["fixture_id"])
        s5 = (m.get("strategies") or {}).get("S5_conservative_coverage") or {}
        ev = s5.get("evaluation") or {}
        out[fid] = bool(ev.get("optimized_top3_hit"))
    return out


def load_coverage_matches(conn: sqlite3.Connection, *, root: Path) -> list[dict[str, Any]]:
    if not _table_exists(conn, "ecse_prediction_snapshots"):
        return []

    has_wde = _table_exists(conn, "worldcup_stored_predictions")
    has_odds = _table_exists(conn, "odds_snapshots")
    opt_hits = _load_optimizer_hits(root)

    query = """
        SELECT ec.fixture_id, ec.generated_at, ec.top_1_score, ec.top_10_scorelines_json,
               ec.lambda_home, ec.lambda_away,
               f.home_team, f.away_team, f.kickoff_utc, f.status, f.round_name,
               fr.home_goals, fr.away_goals, fr.match_outcome_type, fr.penalty_score
    """
    query += ", sp.payload_json" if has_wde else ", NULL AS payload_json"
    query += """
        FROM ecse_prediction_snapshots ec
        JOIN fixtures f ON f.fixture_id = ec.fixture_id
        LEFT JOIN fixture_results fr ON fr.fixture_id = ec.fixture_id
    """
    if has_wde:
        query += " LEFT JOIN worldcup_stored_predictions sp ON sp.fixture_id = ec.fixture_id"
    query += " WHERE f.competition_key = 'world_cup_2026'"

    rows = conn.execute(query).fetchall()
    out: list[dict[str, Any]] = []

    for row in rows:
        r = dict(row)
        fid = int(r["fixture_id"])
        fixture_row = {
            "fixture_id": fid,
            "home_team": r["home_team"],
            "away_team": r["away_team"],
            "kickoff_utc": r["kickoff_utc"],
            "status": r["status"],
            "round_name": r.get("round_name"),
        }
        resolved = resolve_registry_fixture_id(conn, fid)
        registry_id = resolved.get("registry_fixture_id")

        snapshot_top10 = load_snapshot_top10(r.get("top_10_scorelines_json"))
        dist_rows = load_distribution_ranks(conn, registry_id, limit=65)

        res_ctx = result_context(fixture_row, r if r.get("home_goals") is not None else None)
        actual = res_ctx.get("result_90min")
        cov = build_coverage_record(
            actual=actual,
            snapshot_top10=snapshot_top10,
            dist_rows=dist_rows,
        )

        odds_snap_at = None
        odds_source = None
        if has_odds:
            o = conn.execute(
                "SELECT snapshot_at, payload_json FROM odds_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
                (fid,),
            ).fetchone()
            if o:
                odds_snap_at = o["snapshot_at"]
                try:
                    payload = json.loads(o["payload_json"])
                    odds_source = payload.get("source_provider") or payload.get("source")
                except (json.JSONDecodeError, TypeError):
                    odds_source = "odds_snapshots"

        freshness = odds_freshness_meta(
            odds_snapshot_at=odds_snap_at,
            prediction_generated_at=r.get("generated_at"),
            knockout=is_knockout_fixture(fixture_row),
            odds_source=odds_source,
        )

        wde_payload = None
        if r.get("payload_json"):
            try:
                wde_payload = json.loads(r["payload_json"])
            except json.JSONDecodeError:
                wde_payload = None
        wde = extract_wde_markets(wde_payload)

        record = {
            "fixture_id": fid,
            "match": f"{r['home_team']} vs {r['away_team']}",
            "knockout": is_knockout_fixture(fixture_row),
            "actual_90min": actual,
            "outcome": actual_outcome(actual),
            "registry_fixture_id": registry_id,
            "registry_resolve": resolved,
            "coverage": cov,
            "snapshot_lambda": {
                "lambda_home": r.get("lambda_home"),
                "lambda_away": r.get("lambda_away"),
            },
            "wde": wde,
            "odds_freshness": freshness,
            "result_context": res_ctx,
            "baseline_top3_hit": cov.get("in_top3_snapshot"),
            "baseline_top5_hit": cov.get("in_top5_snapshot"),
            "optimized_top3_hit": opt_hits.get(fid),
            "top5_miss_reason": miss_due_to_ranking_or_absence({"actual_90min": actual, "coverage": cov}, topn=5)
            if actual and not cov.get("in_top5_snapshot")
            else "hit",
            "root_cause_category": classify_root_cause(
                {
                    "actual_90min": actual,
                    "coverage": cov,
                    "outcome": actual_outcome(actual),
                    "odds_freshness": freshness,
                    "result_context": res_ctx,
                    "wde": wde,
                }
            )
            if actual
            else "DATA_MISSING",
        }
        out.append(record)
    return out


def run_coverage_analysis(*, db_path: str | None = None, artifacts_dir: str | Path = "artifacts") -> dict[str, Any]:
    settings = get_settings()
    root = Path(__file__).resolve().parents[3]
    conn = connect_readonly(db_path or settings.sqlite_path)
    try:
        matches = load_coverage_matches(conn, root=root)
    finally:
        conn.close()

    finished = [m for m in matches if m.get("actual_90min")]
    summary = aggregate_summary(matches)
    reality = can_89pct_from_candidates(summary)
    top5_misses = [d for m in finished if (d := diagnose_top5_miss(m))]

    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "top10_coverage_1_results.json"
    csv_path = out_dir / "top10_coverage_1_match_level.csv"

    payload = {
        "phase": PHASE,
        "shadow_only": SHADOW_ONLY,
        "match_count": len(matches),
        "finished_count": len(finished),
        "summary": summary,
        "reality_check_89pct": reality,
        "top5_miss_diagnoses": top5_misses,
        "candidate_generation_recommendations": _generation_plan(top5_misses, summary),
        "matches": matches,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    _write_csv(csv_path, finished)

    return {"json_path": str(json_path), "csv_path": str(csv_path), "payload": payload}


def _write_csv(path: Path, finished: list[dict[str, Any]]) -> None:
    fields = [
        "fixture_id",
        "match",
        "actual_90min",
        "actual_total_goals",
        "actual_btts",
        "actual_winner",
        "rank_effective",
        "rank_bucket",
        "in_top3",
        "in_top5",
        "in_top10",
        "in_top20",
        "in_full",
        "baseline_top3_hit",
        "baseline_top5_hit",
        "optimized_top3_hit",
        "top5_miss_reason",
        "root_cause",
        "aet_pen",
        "odds_freshness",
    ]
    from worldcup_predictor.research.top10_coverage.features import rank_bucket

    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for m in finished:
            cov = m.get("coverage") or {}
            outcome = m.get("outcome") or {}
            rank = cov.get("rank_effective")
            w.writerow(
                {
                    "fixture_id": m["fixture_id"],
                    "match": m["match"],
                    "actual_90min": m["actual_90min"],
                    "actual_total_goals": outcome.get("total_goals"),
                    "actual_btts": outcome.get("btts"),
                    "actual_winner": outcome.get("winner"),
                    "rank_effective": rank,
                    "rank_bucket": rank_bucket(rank, in_full=bool(cov.get("in_full_distribution"))),
                    "in_top3": cov.get("in_top3_snapshot"),
                    "in_top5": cov.get("in_top5_snapshot"),
                    "in_top10": cov.get("in_top10_snapshot"),
                    "in_top20": cov.get("in_top20_distribution"),
                    "in_full": cov.get("in_full_distribution"),
                    "baseline_top3_hit": m.get("baseline_top3_hit"),
                    "baseline_top5_hit": m.get("baseline_top5_hit"),
                    "optimized_top3_hit": m.get("optimized_top3_hit"),
                    "top5_miss_reason": m.get("top5_miss_reason"),
                    "root_cause": m.get("root_cause_category"),
                    "aet_pen": bool(
                        (m.get("result_context") or {}).get("ended_in_extra_time")
                        or (m.get("result_context") or {}).get("ended_on_penalties")
                    ),
                    "odds_freshness": (m.get("odds_freshness") or {}).get("freshness_flag"),
                }
            )


def _generation_plan(misses: list[dict[str, Any]], summary: dict[str, Any]) -> list[dict[str, str]]:
    recs: list[dict[str, str]] = []
    cats = {m.get("root_cause_category") for m in misses}
    if "HIGH_GOAL_TAIL_MISSING" in cats or "BTTS_SCORE_MISSING" in cats:
        recs.append(
            {
                "archetype": "high_goal_btts",
                "lines": "3-2, 2-3, 4-1, 4-2",
                "experiment": "Shadow inject into candidate pool when WDE Over+BTTS Yes",
            }
        )
    if "DRAW_RISK_MISSING" in cats:
        recs.append(
            {
                "archetype": "draw_risk",
                "lines": "0-0, 1-1, 2-2",
                "experiment": "Shadow hedge when draw proxy ≥ threshold",
            }
        )
    if "ACTUAL_OUTSIDE_TOP10_CANDIDATE_PROBLEM" in cats:
        recs.append(
            {
                "archetype": "distribution_tail",
                "lines": "Expand Poisson grid tail / ensure 4+ goal lines in stored distribution",
                "experiment": "Audit lambda truncation — shadow only",
            }
        )
    if summary.get("top10_coverage_pct", 0) > summary.get("top5_coverage_pct", 0):
        recs.append(
            {
                "archetype": "ranking_selection",
                "lines": "N/A — scores exist in Top6-10",
                "experiment": "Continue TOP3 optimizer S5; no new candidate generation needed",
            }
        )
    if not recs:
        recs.append(
            {
                "archetype": "none_yet",
                "lines": "Insufficient miss diversity",
                "experiment": "Collect 30+ finished matches before new archetypes",
            }
        )
    return recs
