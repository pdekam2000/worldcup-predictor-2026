"""Load real completed fixtures for Phase 5 (no synthetic outcomes)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.research.bet_coverage_optimizer.phase5.layer_builder import (
    extract_real_market_candidates,
    select_main_and_insurance,
)
from worldcup_predictor.research.ecse_historical_replay.replay_engine import replay_fixture


def _hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def default_source_db() -> Path:
    return project_root() / "data" / "football_intelligence.db"


def default_forward_db() -> Path:
    return project_root() / "data" / "evaluation" / "forward_prediction_tracking.db"


def _open_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def load_frozen_completed(
    forward_db: Path | None = None,
    *,
    top_n: int = 8,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Immutable freezes with actual results — primary forward-evidence stratum."""
    path = forward_db or default_forward_db()
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    if not path.exists():
        return included, [{"reason": "FORWARD_DB_MISSING", "path": str(path)}]

    conn = _open_ro(path)
    conn.row_factory = sqlite3.Row
    try:
        rankings: dict[str, list[tuple[str, float]]] = {}
        for r in conn.execute(
            "SELECT prediction_id, rank, score, probability FROM exact_score_rankings "
            "ORDER BY prediction_id, CAST(rank AS INT)"
        ):
            rankings.setdefault(str(r["prediction_id"]), []).append(
                (str(r["score"]), float(r["probability"] or 0.0))
            )
        results = {
            int(r["fixture_id"]): dict(r)
            for r in conn.execute("SELECT * FROM actual_results")
            if r["actual_score"]
        }
        # earliest freeze per fixture
        by_fx: dict[int, list[dict[str, Any]]] = {}
        for r in conn.execute("SELECT * FROM frozen_predictions"):
            fid = int(r["fixture_id"])
            by_fx.setdefault(fid, []).append(dict(r))

        for fid, cands in by_fx.items():
            cands.sort(key=lambda x: str(x.get("frozen_at") or x.get("generated_at") or ""))
            fr = cands[0]
            pid = str(fr.get("prediction_id"))
            if fid not in results:
                excluded.append({"fixture_id": fid, "reasons": ["MISSING_ACTUAL_SCORE"], "source": "frozen"})
                continue
            top = rankings.get(pid) or []
            if len(top) < 3:
                excluded.append({"fixture_id": fid, "reasons": ["MISSING_TOP_N_RANKINGS"], "source": "frozen"})
                continue
            actual = str(results[fid]["actual_score"]).replace(" ", "")
            # Build synthetic-like raw odds from freeze 1x2 / BTTS / OU when present
            raw = {
                "oddsFT_1": fr.get("odds_home"),
                "oddsFT_X": fr.get("odds_draw"),
                "oddsFT_2": fr.get("odds_away"),
            }
            top_pairs = [(s, p) for s, p in top[:top_n]]
            exact3 = [s for s, _ in top_pairs[:3]]
            cands_m = extract_real_market_candidates(raw, top_n_pairs=top_pairs, exact3=exact3)
            layers = select_main_and_insurance(cands_m, top_n_pairs=top_pairs, exact3=exact3)
            included.append(
                _fixture_record(
                    fixture_id=fid,
                    source="frozen_prematch",
                    league=str(fr.get("competition") or "unknown"),
                    match_name=str(fr.get("match_name") or fid),
                    kickoff=str(fr.get("kickoff") or ""),
                    top_pairs=top_pairs,
                    actual=actual,
                    layers=layers,
                    entropy=float(fr.get("entropy") or 0.0),
                    confidence=float(fr.get("wde_confidence") or fr.get("top5_mass") or 0.0),
                    lambda_total=float(fr.get("total_lambda") or 0.0),
                    btts_probability=float(fr.get("btts_probability") or 0.0),
                    over_probability=float(fr.get("over_probability") or 0.0),
                    odds_home=float(fr.get("odds_home") or 0.0) or None,
                    immutable_parts={"prediction_id": pid, "frozen_at": fr.get("frozen_at")},
                )
            )
    finally:
        conn.close()
    return included, excluded


def iter_historical_ecse_completed(
    source_db: Path | None = None,
    *,
    top_n: int = 8,
    max_fixtures: int = 2500,
) -> Iterator[tuple[dict[str, Any] | None, dict[str, Any] | None]]:
    """
    Yield (fixture|None, exclusion|None) from external historical CSV.

    Predictions = immutable ECSE formulas applied to prematch odds features.
    Outcomes = real completed FT scores. No fabricated odds / no synthetic scores.
    """
    path = source_db or default_source_db()
    if not path.exists():
        yield None, {"reasons": ["SOURCE_DB_MISSING"], "path": str(path)}
        return
    conn = _open_ro(path)
    conn.row_factory = sqlite3.Row
    seen: set[str] = set()
    produced = 0
    try:
        for rec in conn.execute(
            "SELECT row_hash, source_file, raw_row_json FROM external_historical_csv_raw_rows"
        ):
            if produced >= max_fixtures:
                break
            rh = str(rec["row_hash"])
            if rh in seen:
                continue
            seen.add(rh)
            try:
                raw = json.loads(rec["raw_row_json"])
            except json.JSONDecodeError:
                yield None, {"fixture_key": rh, "reasons": ["MALFORMED_RAW_JSON"]}
                continue
            row = replay_fixture(rh, str(rec["source_file"]), raw)
            if row is None:
                yield None, {"fixture_key": rh, "reasons": ["ECSE_REPLAY_INELIGIBLE"]}
                continue
            if not row.leakage_pass:
                yield None, {"fixture_key": rh, "reasons": ["LEAKAGE_FAIL"]}
                continue
            top_pairs = [(x["scoreline"], float(x["probability"])) for x in row.top10[:top_n]]
            if len(top_pairs) < 3:
                yield None, {"fixture_key": rh, "reasons": ["INSUFFICIENT_TOP_N"]}
                continue
            exact3 = [s for s, _ in top_pairs[:3]]
            cands = extract_real_market_candidates(raw, top_n_pairs=top_pairs, exact3=exact3)
            if not cands:
                yield None, {"fixture_key": rh, "reasons": ["NO_REAL_PREMATCH_MARKETS"]}
                continue
            layers = select_main_and_insurance(cands, top_n_pairs=top_pairs, exact3=exact3)
            if not layers.get("main_coverage"):
                yield None, {"fixture_key": rh, "reasons": ["NO_ELIGIBLE_MAIN_COVERAGE"]}
                continue
            produced += 1
            yield (
                _fixture_record(
                    fixture_id=abs(hash(rh)) % 10_000_000,
                    source="ecse_historical_replay_prematch",
                    league=row.league or row.competition,
                    match_name=row.match,
                    kickoff=row.kickoff,
                    top_pairs=top_pairs,
                    actual=row.actual_score,
                    layers=layers,
                    entropy=float(row.entropy),
                    confidence=float(row.top5_mass),
                    lambda_total=float(row.lambda_total),
                    btts_probability=None,
                    over_probability=None,
                    odds_home=float(row.odds_home),
                    immutable_parts={
                        "row_hash": rh,
                        "model_version": row.model_version,
                        "event_date": row.event_date,
                    },
                    all_candidates=cands,
                ),
                None,
            )
    finally:
        conn.close()


def _fixture_record(
    *,
    fixture_id: int,
    source: str,
    league: str,
    match_name: str,
    kickoff: str,
    top_pairs: list[tuple[str, float]],
    actual: str,
    layers: dict[str, Any],
    entropy: float,
    confidence: float,
    lambda_total: float,
    btts_probability: float | None,
    over_probability: float | None,
    odds_home: float | None,
    immutable_parts: dict[str, Any],
    all_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    main = layers.get("main_coverage") or {}
    ins = layers.get("insurance") or {}
    exact3 = list(layers.get("exact3") or [])
    main_scores = list(layers.get("main_coverage_scores") or [])
    ins_scores = list(layers.get("insurance_scores") or [])
    # Research 125 baseline proxy: union of top-N scorelines (not literal 125 tickets)
    baseline_125 = [s for s, _ in top_pairs]

    priced = bool(main.get("odds") and float(main.get("odds") or 0) > 1.0)
    monetary = None
    if priced:
        monetary = {
            "coverage_odds": float(main["odds"]),
            "insurance_odds": float(ins["odds"]) if ins.get("odds") else None,
            "stake": 1.0,
        }

    return {
        "fixture_id": int(fixture_id),
        "source": source,
        "league": league,
        "match_name": match_name,
        "kickoff": kickoff,
        "top_n_scores": [{"score": s, "probability": p} for s, p in top_pairs],
        "exact3": exact3,
        "main_coverage_scores": main_scores,
        "insurance_scores": ins_scores,
        "baseline_125_scores": baseline_125,
        "actual_score": actual,
        "prematch_odds_complete": priced and bool(ins.get("odds")),
        "uses_postmatch_odds": False,
        "kickoff_frozen": True,
        "monetary": monetary,
        "entropy": entropy,
        "confidence": confidence,
        "lambda_total": lambda_total,
        "btts_probability": btts_probability,
        "over_probability": over_probability,
        "odds_home": odds_home,
        "main_market_label": main.get("market_label"),
        "main_market_family": main.get("market_family_key") or main.get("market_type"),
        "main_odds": main.get("odds"),
        "insurance_market_label": ins.get("market_label"),
        "insurance_market_family": ins.get("market_family_key") or ins.get("market_type"),
        "insurance_odds": ins.get("odds"),
        "incremental_uncovered_mass": ins.get("incremental_uncovered_probability_mass"),
        "primary_overlap_ratio": ins.get("primary_overlap_ratio"),
        "coverage_ratio_primary": layers.get("coverage_ratio_primary"),
        "coverage_ratio_with_insurance": layers.get("coverage_ratio_with_insurance"),
        "residual_mass": layers.get("residual_mass"),
        "n_markets_available": layers.get("n_markets_available"),
        "all_candidates": all_candidates or [],
        "immutable_input_hash": _hash(
            {
                "source": source,
                "actual": actual,
                "exact3": exact3,
                "main": main_scores,
                "ins": ins_scores,
                **immutable_parts,
            }
        ),
    }


def build_phase5_corpus(
    *,
    min_fixtures: int = 1000,
    max_historical: int = 2500,
    top_n: int = 8,
    source_db: Path | None = None,
    forward_db: Path | None = None,
) -> dict[str, Any]:
    frozen, frozen_ex = load_frozen_completed(forward_db, top_n=top_n)
    historical: list[dict[str, Any]] = []
    hist_ex: list[dict[str, Any]] = []
    for fx, ex in iter_historical_ecse_completed(source_db, top_n=top_n, max_fixtures=max_historical):
        if ex:
            # Cap excluded list size for artifact readability
            if len(hist_ex) < 500:
                hist_ex.append(ex)
            elif len(hist_ex) == 500:
                hist_ex.append({"reasons": ["EXCLUSION_LIST_TRUNCATED"]})
            continue
        if fx:
            historical.append(fx)

    # Prefer historical scale for primary replay; keep frozen separate for forward evidence
    primary = list(historical)
    enough = len(primary) >= int(min_fixtures)
    corpus_hash = _hash(
        [{"fixture_id": f["fixture_id"], "h": f["immutable_input_hash"]} for f in primary[: min_fixtures + 50]]
    )
    return {
        "research_only": True,
        "min_fixtures_required": int(min_fixtures),
        "enough_historical_data": enough,
        "primary_source": "ecse_historical_replay_prematch",
        "primary_fixtures": primary,
        "n_primary": len(primary),
        "frozen_completed_fixtures": frozen,
        "n_frozen_completed": len(frozen),
        "excluded_frozen": frozen_ex,
        "excluded_historical_sample": hist_ex,
        "n_excluded_historical_reported": len(hist_ex),
        "immutable_corpus_hash": corpus_hash,
        "no_synthetic_outcomes": True,
        "no_fabricated_odds": True,
        "note": (
            "Primary ≥1000 corpus uses immutable ECSE formulas on prematch CSV odds + real FT scores. "
            "Frozen prematch snapshots are retained as a separate forward-evidence stratum."
            if enough
            else f"Only {len(primary)} historical fixtures available; need ≥{min_fixtures}."
        ),
    }
