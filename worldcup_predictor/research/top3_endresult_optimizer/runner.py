"""Batch runner — read-only DB, shadow optimizer backtest artifacts."""

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
from worldcup_predictor.research.top3_endresult_optimizer.candidate_pool import build_candidate_pool
from worldcup_predictor.research.top3_endresult_optimizer.evaluator import (
    aggregate_strategy_metrics,
    evaluate_match_strategy,
    reality_check_89pct,
)
from worldcup_predictor.research.top3_endresult_optimizer.features import PHASE
from worldcup_predictor.research.top3_endresult_optimizer.optimizer import STRATEGIES, optimize_top3
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly

PUBLIC_PUBLISH = False
SHADOW_ONLY = True


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    return row is not None


def load_match_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "ecse_prediction_snapshots"):
        return []

    has_wde = _table_exists(conn, "worldcup_stored_predictions")
    has_odds = _table_exists(conn, "odds_snapshots")

    query = """
        SELECT ec.fixture_id, ec.generated_at, ec.top_1_score,
               ec.top_3_scores_json, ec.top_5_scores_json, ec.top_10_scorelines_json,
               f.home_team, f.away_team, f.kickoff_utc, f.status, f.round_name, f.competition_key,
               fr.home_goals, fr.away_goals, fr.match_outcome_type, fr.penalty_score
    """
    if has_wde:
        query += ", sp.payload_json"
    else:
        query += ", NULL AS payload_json"

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
        raw_top3 = [x["scoreline"] for x in sorted10[:3]]
        raw_top5 = [x["scoreline"] for x in sorted10[:5]]
        top10_lines = [x["scoreline"] for x in sorted10]

        pool = build_candidate_pool(top10=top10, top5_lines=raw_top5, wde=wde)
        res_ctx = result_context(fixture_row, r if r.get("home_goals") is not None else None)
        actual = res_ctx.get("result_90min")

        strategies_out: dict[str, Any] = {}
        for sid in STRATEGIES:
            candidates = optimize_top3(sid, pool, wde)
            ev = evaluate_match_strategy(
                actual_90min=actual,
                raw_top3=raw_top3,
                raw_top5=raw_top5,
                optimized_top3=candidates,
                top10_lines=top10_lines,
                wde=wde,
                ended_aet=res_ctx.get("ended_in_extra_time", False),
                ended_pen=res_ctx.get("ended_on_penalties", False),
            )
            strategies_out[sid] = {"candidates": candidates, "evaluation": ev}

        segment = "knockout" if knockout else "group_stage"
        if not actual:
            segment = "pending"

        out.append(
            {
                "fixture_id": fid,
                "match": f"{r['home_team']} vs {r['away_team']}",
                "segment": segment,
                "knockout": knockout,
                "actual_90min": actual,
                "raw_top1": r.get("top_1_score"),
                "raw_top3": raw_top3,
                "raw_top5": raw_top5,
                "top10_lines": top10_lines,
                "wde": wde,
                "odds_freshness": freshness,
                "result_context": res_ctx,
                "pool_archetype": pool.get("archetype"),
                "strategies": strategies_out,
            }
        )
    return out


def _baseline_audit(finished: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(finished) or 1
    s0_evals = [
        (m["strategies"]["S0_baseline_raw_top3"]["evaluation"])
        for m in finished
        if m["strategies"].get("S0_baseline_raw_top3")
    ]
    top1_hits = sum(1 for m in finished if m.get("actual_90min") == m.get("raw_top1"))
    top3_hits = sum(1 for e in s0_evals if e.get("raw_top3_hit"))
    top5_hits = sum(1 for e in s0_evals if e.get("raw_top5_hit"))
    rank_dist = {f"rank_{i}": 0 for i in range(1, 6)}
    rank_dist["miss"] = 0
    for e in s0_evals:
        b = e.get("actual_rank_bucket") or "miss"
        rank_dist[b] = rank_dist.get(b, 0) + 1
    in_top5_not_top3 = sum(1 for e in s0_evals if e.get("in_top5_outside_top3"))
    cs_top1 = sum(1 for m in finished if _is_cs(m.get("raw_top1")))

    btts_yes_actual = 0
    btts_yes_clean_top1 = 0
    over_actual = 0
    low_top1_on_over = 0
    for m in finished:
        act = m.get("actual_90min")
        if not act:
            continue
        h, a = map(int, act.split("-"))
        if h > 0 and a > 0:
            btts_yes_actual += 1
        if (h + a) > 2:
            over_actual += 1
        wde = m.get("wde") or {}
        top1 = m.get("raw_top1")
        if str(wde.get("pick_btts")).lower().endswith("yes") and _is_cs(top1):
            btts_yes_clean_top1 += 1
        ou = str(wde.get("pick_ou25") or "").lower()
        if "over" in ou and _tg(top1) is not None and _tg(top1) <= 2:
            low_top1_on_over += 1

    return {
        "finished_matches": len(finished),
        "top1_hit_rate_pct": round(100 * top1_hits / n, 1),
        "raw_top3_hit_rate_pct": round(100 * top3_hits / n, 1),
        "raw_top5_hit_rate_pct": round(100 * top5_hits / n, 1),
        "rank_distribution": rank_dist,
        "in_top5_outside_top3_count": in_top5_not_top3,
        "clean_sheet_top1_rate_pct": round(100 * cs_top1 / n, 1),
        "actual_btts_yes_count": btts_yes_actual,
        "wde_btts_yes_clean_top1_count": btts_yes_clean_top1,
        "actual_over_25_count": over_actual,
        "wde_over_low_top1_count": low_top1_on_over,
        "aet_pen_matches": sum(
            1
            for m in finished
            if (m.get("result_context") or {}).get("ended_in_extra_time")
            or (m.get("result_context") or {}).get("ended_on_penalties")
        ),
    }


def _is_cs(line: str | None) -> bool:
    if not line or "-" not in str(line):
        return False
    h, a = map(int, str(line).split("-"))
    return h == 0 or a == 0


def _tg(line: str | None) -> int | None:
    if not line:
        return None
    h, a = map(int, str(line).split("-"))
    return h + a


def _strategy_summary(matches: list[dict[str, Any]]) -> dict[str, Any]:
    finished = [m for m in matches if m.get("actual_90min")]
    summary: dict[str, Any] = {}
    for sid in STRATEGIES:
        evals = [m["strategies"][sid]["evaluation"] for m in finished]
        all_metrics = aggregate_strategy_metrics(evals, "all")
        knockout_evals = [
            m["strategies"][sid]["evaluation"]
            for m in finished
            if m.get("knockout")
        ]
        group_evals = [
            m["strategies"][sid]["evaluation"]
            for m in finished
            if not m.get("knockout")
        ]
        stale_evals = [
            m["strategies"][sid]["evaluation"]
            for m in finished
            if (m.get("odds_freshness") or {}).get("freshness_flag") == "STALE_ODDS"
        ]
        fresh_evals = [
            m["strategies"][sid]["evaluation"]
            for m in finished
            if (m.get("odds_freshness") or {}).get("freshness_flag") == "FRESH_ODDS"
        ]
        summary[sid] = {
            "label": STRATEGIES[sid]["label"],
            "segments": {
                "all": all_metrics,
                "knockout": aggregate_strategy_metrics(knockout_evals, "knockout"),
                "group_stage": aggregate_strategy_metrics(group_evals, "group_stage"),
                "stale_odds": aggregate_strategy_metrics(stale_evals, "stale_odds"),
                "fresh_odds": aggregate_strategy_metrics(fresh_evals, "fresh_odds"),
            },
            "reality_check_89pct": reality_check_89pct(
                all_metrics.get("count") or 0,
                all_metrics.get("top3_hit_count") or 0,
            ),
        }
    return summary


def _best_strategy(summary: dict[str, Any]) -> str:
    best_id = "S0_baseline_raw_top3"
    best_rate = -1.0
    for sid, data in summary.items():
        rate = (data.get("segments") or {}).get("all", {}).get("top3_hit_rate_pct") or 0
        if rate > best_rate:
            best_rate = rate
            best_id = sid
    return best_id


def run_optimizer_backtest(*, db_path: str | None = None, artifacts_dir: str | Path = "artifacts") -> dict[str, Any]:
    settings = get_settings()
    conn = connect_readonly(db_path or settings.sqlite_path)
    try:
        matches = load_match_rows(conn)
    finally:
        conn.close()

    finished = [m for m in matches if m.get("actual_90min")]
    baseline = _baseline_audit(finished)
    strategy_summary = _strategy_summary(matches)
    best_id = _best_strategy(strategy_summary)

    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "top3_endresult_optimizer_1_results.json"
    csv_path = out_dir / "top3_endresult_optimizer_1_results.csv"
    md_path = out_dir / "top3_endresult_optimizer_1_match_level.md"

    payload = {
        "phase": PHASE,
        "shadow_only": SHADOW_ONLY,
        "PUBLIC_PUBLISH": PUBLIC_PUBLISH,
        "match_count": len(matches),
        "finished_count": len(finished),
        "baseline_audit": baseline,
        "strategy_summary": strategy_summary,
        "best_strategy_id": best_id,
        "best_strategy_label": STRATEGIES[best_id]["label"],
        "matches": matches,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    _write_csv(csv_path, matches, finished)
    _write_match_md(md_path, matches, finished, strategy_summary, best_id, baseline)

    return {
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "md_path": str(md_path),
        "payload": payload,
    }


def _write_csv(path: Path, matches: list[dict[str, Any]], finished: list[dict[str, Any]]) -> None:
    fields = [
        "fixture_id",
        "match",
        "segment",
        "actual_90min",
        "raw_top1",
        "raw_top3",
        "raw_top5_hit",
        "actual_ecse_rank",
    ] + [f"{sid}_top3" for sid in STRATEGIES] + [f"{sid}_hit" for sid in STRATEGIES]

    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for m in finished:
            row = {
                "fixture_id": m["fixture_id"],
                "match": m["match"],
                "segment": m["segment"],
                "actual_90min": m["actual_90min"],
                "raw_top1": m["raw_top1"],
                "raw_top3": "|".join(m["raw_top3"]),
                "raw_top5_hit": m["strategies"]["S0_baseline_raw_top3"]["evaluation"].get("raw_top5_hit"),
                "actual_ecse_rank": m["strategies"]["S0_baseline_raw_top3"]["evaluation"].get("actual_ecse_rank"),
            }
            for sid in STRATEGIES:
                cands = m["strategies"][sid]["candidates"]
                ev = m["strategies"][sid]["evaluation"]
                row[f"{sid}_top3"] = "|".join(cands)
                row[f"{sid}_hit"] = ev.get("optimized_top3_hit")
            w.writerow(row)


def _write_match_md(
    path: Path,
    matches: list[dict[str, Any]],
    finished: list[dict[str, Any]],
    summary: dict[str, Any],
    best_id: str,
    baseline: dict[str, Any],
) -> None:
    lines = [
        "# Top3 End Result Optimizer — Match Level",
        "",
        f"Finished matches: **{len(finished)}**",
        f"Best strategy: **{best_id}** — {STRATEGIES[best_id]['label']}",
        "",
        "## Strategy Hit Rates (all finished)",
        "",
        "| Strategy | Top3 Hit Rate | Hits | Gained vs raw | Lost vs raw |",
        "|----------|---------------|------|---------------|-------------|",
    ]
    for sid, data in summary.items():
        seg = data["segments"]["all"]
        lines.append(
            f"| {sid} | {seg.get('top3_hit_rate_pct')}% | "
            f"{seg.get('top3_hit_count')}/{seg.get('count')} | "
            f"+{seg.get('gained_hits_vs_raw', 0)} | -{seg.get('lost_hits_vs_raw', 0)} |"
        )
    lines += ["", "## Per-Match", "", "| Match | Actual | Raw Top3 | Best Top3 | Raw hit | Best hit |", "|-------|--------|----------|-----------|---------|----------|"]
    for m in sorted(finished, key=lambda x: x["match"]):
        raw_ev = m["strategies"]["S0_baseline_raw_top3"]["evaluation"]
        best_cands = m["strategies"][best_id]["candidates"]
        best_ev = m["strategies"][best_id]["evaluation"]
        lines.append(
            f"| {m['match']} | {m['actual_90min']} | {' · '.join(m['raw_top3'])} | "
            f"{' · '.join(best_cands)} | {'Y' if raw_ev.get('raw_top3_hit') else 'N'} | "
            f"{'Y' if best_ev.get('optimized_top3_hit') else 'N'} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
