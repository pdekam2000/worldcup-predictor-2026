"""Batch runner — load DB read-only, emit shadow artifacts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly
from worldcup_predictor.research.ecse_rerank.evaluator import evaluate_shadow_vs_baseline, evaluate_single_match
from worldcup_predictor.research.ecse_rerank.features import (
    extract_wde_markets,
    is_knockout_fixture,
    odds_freshness_meta,
    parse_top10,
    result_context,
)
from worldcup_predictor.research.ecse_rerank.reranker import rerank_ecse_top10_shadow

PHASE = "ECSE-RERANK-1"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    return row is not None


def load_evaluation_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "ecse_prediction_snapshots"):
        return []

    has_wde = _table_exists(conn, "worldcup_stored_predictions")
    has_odds = _table_exists(conn, "odds_snapshots")

    query = """
        SELECT
            ec.fixture_id,
            ec.generated_at AS ecse_generated_at,
            ec.top_1_score,
            ec.top_3_scores_json,
            ec.top_5_scores_json,
            ec.top_10_scorelines_json,
            ec.prediction_source,
            f.home_team, f.away_team, f.kickoff_utc, f.status, f.round_name,
            fr.home_goals, fr.away_goals, fr.final_score,
            fr.match_outcome_type, fr.penalty_score
    """
    if has_wde:
        query += ", sp.payload_json, sp.predicted_at AS wde_predicted_at"
    else:
        query += ", NULL AS payload_json, NULL AS wde_predicted_at"

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
                    odds_source = payload.get("source_provider") or payload.get("source") or "odds_snapshots"
                except (json.JSONDecodeError, TypeError):
                    odds_source = "odds_snapshots"

        freshness = odds_freshness_meta(
            odds_snapshot_at=odds_snap_at,
            prediction_generated_at=r.get("ecse_generated_at"),
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
        baseline_top3 = [x["scoreline"] for x in sorted(top10, key=lambda z: z.get("rank", 99))[:3]]
        baseline_top5 = [x["scoreline"] for x in sorted(top10, key=lambda z: z.get("rank", 99))[:5]]

        shadow = rerank_ecse_top10_shadow(
            top_10=top10,
            wde_1x2=wde.get("pick_1x2"),
            wde_btts=wde.get("pick_btts"),
            wde_ou25=wde.get("pick_ou25"),
            ecse_top1=r.get("top_1_score"),
            odds_freshness=freshness,
            fixture_id=fid,
        )

        res_ctx = result_context(fixture_row, r if r.get("home_goals") is not None else None)
        actual = res_ctx.get("result_90min")

        evaluation = evaluate_single_match(
            actual_90min=actual,
            baseline_top1=r.get("top_1_score"),
            baseline_top3=baseline_top3,
            baseline_top5=baseline_top5,
            shadow_top1=shadow.get("shadow", {}).get("top_1"),
            shadow_top3=shadow.get("shadow", {}).get("top_3") or [],
            shadow_top5=shadow.get("shadow", {}).get("top_5") or [],
            wde_1x2=wde.get("pick_1x2"),
            wde_btts=wde.get("pick_btts"),
            wde_ou=wde.get("pick_ou25"),
            ended_aet=res_ctx.get("ended_in_extra_time", False),
            ended_pen=res_ctx.get("ended_on_penalties", False),
        )

        segment = "knockout" if knockout else "group_stage"
        if r.get("home_goals") is None:
            segment = "pending"

        out.append(
            {
                "fixture_id": fid,
                "match": f"{r['home_team']} vs {r['away_team']}",
                "segment": segment if actual else "pending",
                "knockout": knockout,
                "odds_freshness": freshness,
                "result_context": res_ctx,
                "wde": wde,
                "baseline_top1": r.get("top_1_score"),
                "shadow": shadow,
                "evaluation": evaluation,
            }
        )
    return out


def run_shadow_analysis(*, db_path: str | None = None, artifacts_dir: str | Path = "artifacts") -> dict[str, Any]:
    settings = get_settings()
    conn = connect_readonly(db_path or settings.sqlite_path)
    try:
        rows = load_evaluation_rows(conn)
    finally:
        conn.close()

    finished = [r for r in rows if (r.get("evaluation") or {}).get("evaluated")]
    knockout_rows = [r for r in finished if r.get("knockout")]
    group_rows = [r for r in finished if not r.get("knockout")]

    summary = evaluate_shadow_vs_baseline(rows)
    summary["segments"]["knockout"] = evaluate_shadow_vs_baseline(knockout_rows)["segments"].get("all", {})
    summary["segments"]["group_stage"] = evaluate_shadow_vs_baseline(group_rows)["segments"].get("all", {})

    # Baseline audit aggregates
    audit = _baseline_audit(finished)

    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "ecse_rerank_1_shadow_results.json"
    jsonl_path = out_dir / "ecse_rerank_1_shadow_results.jsonl"

    payload = {
        "phase": PHASE,
        "shadow_only": True,
        "PUBLIC_PUBLISH": False,
        "match_count": len(rows),
        "finished_count": len(finished),
        "summary": summary,
        "baseline_audit": audit,
        "examples": _pick_examples(finished),
        "matches": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    return {
        "json_path": str(json_path),
        "jsonl_path": str(jsonl_path),
        "payload": payload,
    }


def _baseline_audit(finished: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(finished) or 1
    clean_top1 = sum(1 for r in finished if _is_cs(r.get("baseline_top1")))
    low_score_top1 = sum(1 for r in finished if _tg(r.get("baseline_top1")) is not None and _tg(r.get("baseline_top1")) <= 2)
    btts_yes_clean = 0
    over_low = 0
    goal_err = []
    for r in finished:
        wde = r.get("wde") or {}
        top1 = r.get("baseline_top1")
        if wde.get("pick_btts") == "yes" and _is_cs(top1):
            btts_yes_clean += 1
        ou = str(wde.get("pick_ou25") or "").lower()
        if "over" in ou and (_tg(top1) or 99) <= 2:
            over_low += 1
        ev = r.get("evaluation") or {}
        if ev.get("baseline_goal_error") is not None:
            goal_err.append(ev["baseline_goal_error"])

    ev_rows = [r.get("evaluation") for r in finished]
    def hit_rate(key):
        t = sum(1 for e in ev_rows if e.get(key) is not None)
        h = sum(1 for e in ev_rows if e.get(key) is True)
        return round(100 * h / t, 1) if t else None

    return {
        "finished_matches": len(finished),
        "baseline_top1_hit_pct": hit_rate("baseline_top1_hit"),
        "baseline_top3_hit_pct": hit_rate("baseline_top3_hit"),
        "baseline_top5_hit_pct": hit_rate("baseline_top5_hit"),
        "clean_sheet_top1_rate_pct": round(100 * clean_top1 / n, 1),
        "low_score_top1_rate_pct": round(100 * low_score_top1 / n, 1),
        "avg_goal_underestimation": round(sum(goal_err) / len(goal_err), 2) if goal_err else None,
        "wde_btts_yes_but_clean_top1": btts_yes_clean,
        "wde_over_but_low_top1": over_low,
        "aet_pen_matches": sum(
            1 for r in finished
            if (r.get("result_context") or {}).get("ended_in_extra_time")
            or (r.get("result_context") or {}).get("ended_on_penalties")
        ),
    }


def _pick_examples(finished: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wanted = {1567309, 1567307, 1567308}  # Portugal, England, Belgium
    examples = []
    for r in finished:
        if int(r["fixture_id"]) in wanted:
            examples.append(
                {
                    "fixture_id": r["fixture_id"],
                    "match": r["match"],
                    "actual": (r.get("evaluation") or {}).get("actual_90min"),
                    "baseline_top1": r.get("baseline_top1"),
                    "shadow_top1": (r.get("shadow") or {}).get("shadow", {}).get("top_1"),
                    "shadow_top3": (r.get("shadow") or {}).get("shadow", {}).get("top_3"),
                    "wde": r.get("wde"),
                    "rank_changed": (r.get("shadow") or {}).get("rank_changed"),
                }
            )
    return examples


def _is_cs(line: str | None) -> bool:
    if not line or "-" not in str(line):
        return False
    h, a = map(int, str(line).split("-"))
    return h == 0 or a == 0


def _tg(line: str | None) -> int | None:
    if not line or "-" not in str(line):
        return None
    h, a = map(int, str(line).split("-"))
    return h + a
