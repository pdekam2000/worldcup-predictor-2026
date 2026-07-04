"""Batch runner — feature table + selector backtest."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_rerank.features import (
    extract_wde_markets,
    is_knockout_fixture,
    odds_freshness_meta,
    parse_top10,
    result_context,
)
from worldcup_predictor.research.top10_to_top3_selector.evaluator import (
    aggregate_metrics,
    evaluate_selection,
    promotion_gate_simulation,
)
from worldcup_predictor.research.top10_to_top3_selector.features import (
    PHASE,
    build_candidate_features,
    inject_tail_candidates,
)
from worldcup_predictor.research.top10_to_top3_selector.selectors import STRATEGIES, select_top3, strategy_a_raw_top3
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly

SHADOW_ONLY = True
PUBLIC_PUBLISH = False


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    return row is not None


def load_finished_matches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "ecse_prediction_snapshots"):
        return []

    has_wde = _table_exists(conn, "worldcup_stored_predictions")
    has_odds = _table_exists(conn, "odds_snapshots")

    query = """
        SELECT ec.fixture_id, ec.generated_at, ec.top_10_scorelines_json,
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
        knockout = is_knockout_fixture(fixture_row)

        odds_snap_at = odds_source = None
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
            knockout=knockout,
            odds_source=odds_source,
        )

        wde_payload = None
        if r.get("payload_json"):
            try:
                wde_payload = json.loads(r["payload_json"])
            except json.JSONDecodeError:
                wde_payload = None
        wde = extract_wde_markets(wde_payload)

        top10 = parse_top10(r.get("top_10_scorelines_json"))
        sorted10 = sorted(top10, key=lambda x: x.get("rank", 99))
        res_ctx = result_context(fixture_row, r if r.get("home_goals") is not None else None)
        actual = res_ctx.get("result_90min")

        base_features = build_candidate_features(
            fixture_id=fid,
            match=f"{r['home_team']} vs {r['away_team']}",
            top10=sorted10,
            wde=wde,
            knockout=knockout,
            odds_freshness=freshness,
        )
        injected_features = inject_tail_candidates(
            base_features,
            wde,
            fixture_id=fid,
            match=f"{r['home_team']} vs {r['away_team']}",
            knockout=knockout,
            odds_freshness=freshness,
        )

        out.append(
            {
                "fixture_id": fid,
                "match": f"{r['home_team']} vs {r['away_team']}",
                "segment": "knockout" if knockout else "group_stage",
                "knockout": knockout,
                "actual_90min": actual,
                "raw_top3": strategy_a_raw_top3(base_features, wde),
                "top10_lines": [c["scoreline"] for c in sorted10],
                "wde": wde,
                "odds_freshness": freshness,
                "result_context": res_ctx,
                "candidate_features": base_features,
                "candidate_features_with_tail": injected_features,
            }
        )
    return out


def run_selector_backtest(*, db_path: str | None = None, artifacts_dir: str | Path = "artifacts") -> dict[str, Any]:
    settings = get_settings()
    conn = connect_readonly(db_path or settings.sqlite_path)
    try:
        matches = load_finished_matches(conn)
    finally:
        conn.close()

    finished = [m for m in matches if m.get("actual_90min")]
    feature_rows: list[dict[str, Any]] = []
    for m in matches:
        feature_rows.extend(m.get("candidate_features") or [])

    strategy_results: dict[str, Any] = {}
    match_level: list[dict[str, Any]] = []

    for sid, spec in STRATEGIES.items():
        evals: list[dict[str, Any]] = []
        for m in finished:
            wde = m.get("wde") or {}
            pool = (
                m.get("candidate_features_with_tail")
                if sid == "F_hybrid_tail_injection"
                else m.get("candidate_features")
            ) or []
            selected = select_top3(sid, pool, wde)
            ev = evaluate_selection(
                actual_90min=m.get("actual_90min"),
                raw_top3=m.get("raw_top3") or [],
                selected_top3=selected,
                candidates=pool,
                wde=wde,
                ended_aet=(m.get("result_context") or {}).get("ended_in_extra_time", False),
                ended_pen=(m.get("result_context") or {}).get("ended_on_penalties", False),
            )
            ev["strategy_id"] = sid
            evals.append(ev)
            match_level.append(
                {
                    "fixture_id": m["fixture_id"],
                    "match": m["match"],
                    "strategy_id": sid,
                    "actual_90min": m.get("actual_90min"),
                    "raw_top3": "|".join(m.get("raw_top3") or []),
                    "selected_top3": "|".join(selected),
                    "raw_hit": ev.get("raw_top3_hit"),
                    "selected_hit": ev.get("selected_top3_hit"),
                    "gained": ev.get("gained_vs_raw"),
                    "lost": ev.get("lost_vs_raw"),
                    "rank_rescue": ev.get("rank_6_10_rescue"),
                    "actual_rank": ev.get("actual_ecse_rank"),
                    "in_top10": ev.get("in_top10"),
                }
            )

        segments = {
            "all": aggregate_metrics(evals, "all"),
            "knockout": aggregate_metrics(
                [e for e, m in zip(evals, finished) if m.get("knockout")], "knockout"
            ),
            "group_stage": aggregate_metrics(
                [e for e, m in zip(evals, finished) if not m.get("knockout")], "group_stage"
            ),
            "stale_odds": aggregate_metrics(
                [
                    e
                    for e, m in zip(evals, finished)
                    if (m.get("odds_freshness") or {}).get("freshness_flag") == "STALE_ODDS"
                ],
                "stale_odds",
            ),
            "aet_pen_flagged": aggregate_metrics(
                [e for e in evals if e.get("ended_in_extra_time") or e.get("ended_on_penalties")],
                "aet_pen_flagged",
            ),
            "aet_pen_excluded": aggregate_metrics(
                [e for e in evals if not e.get("ended_in_extra_time") and not e.get("ended_on_penalties")],
                "aet_pen_excluded",
            ),
        }
        strategy_results[sid] = {"label": spec["label"], "segments": segments, "evaluations": evals}

    best_id = max(
        STRATEGIES.keys(),
        key=lambda sid: (
            strategy_results[sid]["segments"]["all"].get("top3_hit_rate_pct") or 0,
            strategy_results[sid]["segments"]["all"].get("delta_vs_raw_pp") or 0,
        ),
    )
    best_metrics = strategy_results[best_id]["segments"]["all"]
    raw_metrics = strategy_results["A_raw_top3"]["segments"]["all"]

    summary = {
        "finished_matches": len(finished),
        "raw_top3_hit_rate_pct": raw_metrics.get("top3_hit_rate_pct"),
        "top10_coverage_pct": raw_metrics.get("top10_coverage_pct"),
        "best_strategy_id": best_id,
        "best_top3_hit_rate_pct": best_metrics.get("top3_hit_rate_pct"),
        "best_delta_vs_raw_pp": best_metrics.get("delta_vs_raw_pp"),
        "pct_of_top10_ceiling": best_metrics.get("pct_of_top10_ceiling"),
    }

    gate = promotion_gate_simulation(summary, best_metrics)

    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    feature_path = out_dir / "top10_to_top3_selector_1_feature_table.csv"
    json_path = out_dir / "top10_to_top3_selector_1_results.json"
    csv_path = out_dir / "top10_to_top3_selector_1_match_level.csv"

    _write_feature_csv(feature_path, feature_rows)
    _write_match_csv(csv_path, match_level)

    payload = {
        "phase": PHASE,
        "shadow_only": SHADOW_ONLY,
        "PUBLIC_PUBLISH": PUBLIC_PUBLISH,
        "match_count": len(matches),
        "finished_count": len(finished),
        "summary": summary,
        "strategy_results": strategy_results,
        "promotion_gate": gate,
        "key_cases": _key_cases(finished, strategy_results),
        "matches": matches,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    return {
        "feature_path": str(feature_path),
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "payload": payload,
    }


def _key_cases(finished: list[dict[str, Any]], strategy_results: dict[str, Any]) -> dict[str, Any]:
    targets = {
        1565176: "Germany vs Paraguay",
        1567307: "England vs Congo DR",
        1567308: "Belgium vs Senegal",
    }
    out: dict[str, Any] = {}
    for fid, label in targets.items():
        m = next((x for x in finished if int(x["fixture_id"]) == fid), None)
        if not m:
            continue
        case: dict[str, Any] = {
            "match": label,
            "actual": m.get("actual_90min"),
            "raw_top3": m.get("raw_top3"),
            "actual_rank": None,
            "strategies": {},
        }
        lines = m.get("top10_lines") or []
        if m.get("actual_90min") in lines:
            case["actual_rank"] = lines.index(m["actual_90min"]) + 1
        for sid in STRATEGIES:
            idx = next(i for i, fm in enumerate(finished) if int(fm["fixture_id"]) == fid)
            ev = strategy_results[sid]["evaluations"][idx]
            case["strategies"][sid] = {
                "selected_top3": select_top3(
                    sid,
                    m.get("candidate_features_with_tail")
                    if sid == "F_hybrid_tail_injection"
                    else m.get("candidate_features"),
                    m.get("wde") or {},
                ),
                "hit": ev.get("selected_top3_hit"),
                "gained_vs_raw": ev.get("gained_vs_raw"),
            }
        out[str(fid)] = case
    return out


def _write_feature_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _write_match_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
