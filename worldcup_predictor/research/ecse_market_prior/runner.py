"""Orchestrator for ECSE-MARKET-PRIOR-SHADOW-1."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_live.prediction_builder import build_odds_feature_row
from worldcup_predictor.research.ecse_market_prior.dataset import (
    PHASE,
    build_canonical_dataset,
    load_canonical_dataset_from_db,
)
from worldcup_predictor.research.ecse_market_prior.evaluation import (
    production_fixture_diagnostics,
    run_walk_forward_shadow,
)

ARTIFACT_DIR = Path("artifacts/ecse_market_prior_shadow_1")
REPORT_PATH = Path("ECSE_MARKET_PRIOR_SHADOW_1_REPORT.md")

PRODUCTION_FIXTURES = [
    {"fixture_id": 1567310, "match": "Colombia vs Ghana"},
    {"fixture_id": 1567824, "match": "Canada vs Morocco"},
    {"fixture_id": 1569870, "match": "Paraguay vs France"},
    {"fixture_id": 1568100, "match": "Brazil vs Norway"},
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _load_raw_json_map(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    out: dict[str, dict[str, Any]] = {}
    for row in conn.execute("SELECT row_hash, raw_row_json FROM external_historical_csv_raw_rows"):
        try:
            out[str(row["row_hash"])] = json.loads(row["raw_row_json"])
        except json.JSONDecodeError:
            continue
    return out


def _fetch_production_ecse_top3(conn: sqlite3.Connection, fixture_id: int) -> list[str]:
    row = conn.execute(
        """
        SELECT top_10_scorelines_json, top_3_scores_json
        FROM ecse_prediction_snapshots
        WHERE fixture_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return []
    for col in (row[1], row[0]):
        if not col:
            continue
        try:
            data = json.loads(col)
            if isinstance(data, list) and data:
                if isinstance(data[0], dict):
                    return [str(x.get("scoreline")) for x in data[:3]]
                return [str(x) for x in data[:3]]
        except json.JSONDecodeError:
            continue
    return []


def _fetch_production_odds(conn: sqlite3.Connection, fixture_id: int) -> tuple[float | None, float | None, float | None]:
    features = build_odds_feature_row(conn, fixture_id)
    if not features:
        return None, None, None
    return (
        features.get("ft_home_closing"),
        features.get("ft_draw_closing"),
        features.get("ft_away_closing"),
    )


def _recommendation(payload: dict[str, Any]) -> str:
    holdout = payload.get("walk_forward", {}).get("holdout_metrics", {})
    strategies = holdout.get("strategies", {})
    base = strategies.get("A_baseline_ecse", {}).get("baseline", {})
    blend = strategies.get("B_market_blend", {}).get("strategy", {})
    div = strategies.get("C_diversified_top3", {}).get("strategy", {})
    tail = strategies.get("D_tail_calibration", {}).get("strategy", {})

    base_top3 = base.get("top3_hit_pct", 0.0)
    improvements = {
        "blend": blend.get("top3_hit_pct", 0.0) - base_top3,
        "diversify": div.get("top3_hit_pct", 0.0) - base_top3,
        "tail": tail.get("top3_hit_pct", 0.0) - base_top3,
    }
    nat = payload.get("dataset_summary", {}).get("segments", {}).get("national_teams", 0)
    if not payload.get("validation", {}).get("passed", True):
        failed_names = [c.get("name") for c in payload.get("validation", {}).get("failed", [])]
        structural = {"dataset_rows_positive", "no_duplicate_row_hash", "walk_forward_config_present", "holdout_metrics_present"}
        if structural & set(failed_names):
            return "VALIDATION_FAILED"

    best_name = max(improvements, key=improvements.get)
    best_delta = improvements[best_name]
    if nat < 50:
        if best_delta >= 2.0:
            if best_name == "blend":
                return "MARKET_PRIOR_BLEND_PROMISING"
            if best_name == "diversify":
                return "MARKET_PRIOR_DIVERSIFICATION_PROMISING"
            if best_name == "tail":
                return "MARKET_PRIOR_TAIL_CALIBRATION_PROMISING"
        return "NEED_MORE_NATIONAL_TEAM_DATA"
    if best_delta < 0.25:
        if improvements["tail"] >= 0.25:
            return "MARKET_PRIOR_TAIL_CALIBRATION_PROMISING"
        if max(improvements.values()) <= 0:
            return "MARKET_PRIOR_NO_VALUE"
        return "MARKET_PRIOR_DIAGNOSTIC_ONLY"
    if best_name == "blend":
        return "MARKET_PRIOR_BLEND_PROMISING"
    if best_name == "diversify":
        return "MARKET_PRIOR_DIVERSIFICATION_PROMISING"
    return "MARKET_PRIOR_TAIL_CALIBRATION_PROMISING"


def render_report(payload: dict[str, Any]) -> str:
    rec = payload.get("recommendation", "MARKET_PRIOR_NO_VALUE")
    wf = payload.get("walk_forward", {})
    holdout = wf.get("holdout_metrics", {})
    strategies = holdout.get("strategies", {})
    lines = [
        "# ECSE Market Prior Shadow Research — ECSE-MARKET-PRIOR-SHADOW-1",
        "",
        f"**Generated:** {payload.get('generated_at_utc')}",
        "**Mode:** research-only shadow — production ECSE unchanged",
        "",
        f"**Final recommendation:** `{rec}`",
        "",
        "## Part A — Canonical Dataset",
        "",
        f"- Rows: **{payload['dataset_summary'].get('row_count', 0):,}**",
        f"- Date range: {payload['dataset_summary'].get('date_min')} → {payload['dataset_summary'].get('date_max')}",
        f"- Duplicate row_hash: {payload['dataset_summary'].get('duplicate_row_hash_count', 0)}",
        "",
        "## Part I — Walk-Forward Backtest (chronological, no future leakage)",
        "",
        f"- Train N: {wf.get('config', {}).get('train_n')}",
        f"- Validation N: {wf.get('config', {}).get('validation_n')}",
        f"- Holdout N: {wf.get('config', {}).get('holdout_n')}",
        f"- Tuned alpha (validation only): **{wf.get('tuned_alpha')}**",
        "",
        "### Holdout strategy comparison",
        "",
        "| Strategy | N | Top1 % | Top3 % | Top5 % |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, block in strategies.items():
        strat = block.get("strategy") or block.get("baseline") or {}
        lines.append(
            f"| {name} | {strat.get('n', block.get('n_evaluated', '-'))} | {strat.get('top1_hit_pct', '-')} | {strat.get('top3_hit_pct', '-')} | {strat.get('top5_hit_pct', '-')} |"
        )

    lines += ["", "### Part J — Top3 set agreement (ECSE vs market prior)", ""]
    for bucket, stats in (wf.get("agreement_analysis") or {}).items():
        lines.append(
            f"- **{bucket}**: N={stats.get('n')} Top1={stats.get('top1_hit_pct')}% Top3={stats.get('top3_hit_pct')}%"
        )

    lines += ["", "### Part D — K comparison (holdout baseline ECSE)", ""]
    for k, stats in (wf.get("k_comparison") or {}).items():
        lines.append(f"- K={k}: Top3={stats.get('top3_hit_pct')}% (N={stats.get('n')})")

    lines += ["", "### Part E — Time weighting (holdout blend)", ""]
    for scheme, stats in (wf.get("time_weighting_comparison") or {}).items():
        lines.append(f"- {scheme}: Top3={stats.get('top3_hit_pct')}% (N={stats.get('n')})")

    lines += ["", "### Part N — Negative controls", ""]
    for name, stats in (wf.get("negative_controls") or {}).items():
        lines.append(f"- {name}: Top3={stats.get('top3_hit_pct')}% (N={stats.get('n')})")

    lines += ["", "## Part M — Production controlled snapshot diagnostics (read-only)", ""]
    for diag in payload.get("production_diagnostics", []):
        lines += [
            f"### {diag.get('match')} ({diag.get('fixture_id')})",
            f"- Status: **{diag.get('status') or diag.get('agreement_class')}**",
            f"- ECSE Top3: {diag.get('ecse_top3')}",
            f"- Market prior Top5: {diag.get('market_prior_top5')}",
            f"- Set overlap: {diag.get('set_overlap')}",
            "",
        ]

    lines += [
        "",
        "## Answers",
        "",
        f"1. Top1 improvement from market prior blend: { _delta(strategies, 'top1_hit_pct') }",
        f"2. Top3 improvement: { _delta(strategies, 'top3_hit_pct') }",
        f"3. Top5 improvement: { _delta(strategies, 'top5_hit_pct') }",
        f"4. Best K (by Top3 on sampled holdout): { _best_k(wf.get('k_comparison', {})) }",
        f"5. Recency weighting helps: { _recency_helps(wf.get('time_weighting_comparison', {})) }",
        f"6. Full Top3 agreement predictive: see agreement buckets above",
        f"7. Margin tail: underestimated cases logged = {wf.get('margin_analysis', {}).get('underestimated_count')}",
        f"8. Direct blending: {strategies.get('B_market_blend', {}).get('strategy', {}).get('top3_hit_pct')}% Top3",
        f"9. Diversification: {strategies.get('C_diversified_top3', {}).get('strategy', {}).get('top3_hit_pct')}% Top3",
        f"10. Tail calibration: {strategies.get('D_tail_calibration', {}).get('strategy', {}).get('top3_hit_pct')}% Top3",
        f"11. National-team evidence: insufficient in close-band historical source (domestic-heavy)",
        f"12. Safest next step: use as **diagnostic overlay** only; do not promote without national-team coverage",
        "",
        f"**STOP — no production promotion. Recommendation: `{rec}`**",
    ]
    return "\n".join(lines)


def _delta(strategies: dict, key: str) -> str:
    base = strategies.get("A_baseline_ecse", {}).get("baseline", {}).get(key, 0)
    blend = strategies.get("B_market_blend", {}).get("strategy", {}).get(key, 0)
    return f"{blend - base:+.2f} pp (blend vs baseline)"


def _best_k(k_comp: dict) -> str:
    if not k_comp:
        return "unknown"
    best = max(k_comp.items(), key=lambda x: x[1].get("top3_hit_pct", 0))
    return f"K={best[0]} ({best[1].get('top3_hit_pct')}%)"

def _recency_helps(tw: dict) -> str:
    if not tw:
        return "unknown"
    equal = tw.get("equal", {}).get("top3_hit_pct", 0)
    best = max(tw.values(), key=lambda x: x.get("top3_hit_pct", 0))
    return "Yes" if best.get("top3_hit_pct", 0) > equal + 0.25 else "No / marginal"


def run_shadow_research(
    conn: sqlite3.Connection,
    *,
    artifact_dir: Path | None = None,
    report_path: Path | None = None,
    max_eval_per_split: int = 1200,
) -> dict[str, Any]:
    artifact_dir = artifact_dir or ARTIFACT_DIR
    report_path = report_path or REPORT_PATH
    artifact_dir.mkdir(parents=True, exist_ok=True)

    dataset, summary = build_canonical_dataset(
        conn, summary_path=artifact_dir / "ecse_market_prior_dataset_summary.json"
    )
    raw_map = _load_raw_json_map(conn)

    wf = run_walk_forward_shadow(dataset, raw_map, max_eval_per_split=max_eval_per_split)
    wf_dict = {
        "config": wf.config,
        "tuned_alpha": wf.tuned_alpha,
        "train_metrics": wf.train_metrics,
        "validation_metrics": wf.validation_metrics,
        "holdout_metrics": wf.holdout_metrics,
        "agreement_analysis": wf.agreement_analysis,
        "margin_analysis": wf.margin_analysis,
        "negative_controls": wf.negative_controls,
        "k_comparison": wf.k_comparison,
        "time_weighting_comparison": wf.time_weighting_comparison,
        "eval_rows_sample": wf.eval_rows_sample,
    }
    (artifact_dir / "walk_forward_results.json").write_text(
        json.dumps(wf_dict, indent=2), encoding="utf-8"
    )

    production_diag = []
    for fx in PRODUCTION_FIXTURES:
        fid = fx["fixture_id"]
        oh, od, oa = _fetch_production_odds(conn, fid)
        ecse_top3 = _fetch_production_ecse_top3(conn, fid)
        production_diag.append(
            production_fixture_diagnostics(
                fixture_id=fid,
                match_name=fx["match"],
                odds_home=oh,
                odds_draw=od,
                odds_away=oa,
                ecse_top3=ecse_top3,
                dataset=dataset,
            )
        )
    (artifact_dir / "production_diagnostics.json").write_text(
        json.dumps(production_diag, indent=2), encoding="utf-8"
    )

    payload = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "dataset_summary": summary,
        "walk_forward": wf_dict,
        "production_diagnostics": production_diag,
        "validation": {},
        "recommendation": None,
    }
    (artifact_dir / "shadow_research_payload.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    return payload


def finalize_report(payload: dict[str, Any], *, report_path: Path | None = None) -> str:
    report_path = report_path or REPORT_PATH
    payload["recommendation"] = _recommendation(payload)
    report_path.write_text(render_report(payload), encoding="utf-8")
    return payload["recommendation"]
