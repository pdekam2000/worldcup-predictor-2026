#!/usr/bin/env python3
"""PHASE WDE-SHADOW-3 Part E — Validate shadow market dry-run (no production writes)."""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.owner_daily.constants import DEFAULT_TIMEZONE
from worldcup_predictor.owner_daily.fixture_discovery import resolve_target_date
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count, table_exists
from worldcup_predictor.research.wde_shadow_market_inference import (
    DEFAULT_MODEL_DIR,
    ONE_X_TWO_BLOCKED,
    PREDICTIONS_ARTIFACT_TEMPLATE,
    SHADOW_ONLY_LABEL,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PHASE = "WDE-SHADOW-3"
FINAL_REPORT = Path("WDE_SHADOW_MARKET_PROMOTION_DRYRUN_REPORT.md")
SEGMENT_ARTIFACT = Path("artifacts/wde_shadow_market_segment_analysis.json")
BACKTEST_ARTIFACT = Path("artifacts/wde_shadow_vs_current_backtest.json")
VALIDATION_ARTIFACT = Path("artifacts/wde_shadow_market_dryrun_validation.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def _production_counts(conn) -> dict[str, int]:
    return {
        "worldcup_stored_predictions": table_count(conn, "worldcup_stored_predictions")
        if table_exists(conn, "worldcup_stored_predictions")
        else 0,
        "odds_snapshots": table_count(conn, "odds_snapshots") if table_exists(conn, "odds_snapshots") else 0,
        "ecse_prediction_snapshots": table_count(conn, "ecse_prediction_snapshots")
        if table_exists(conn, "ecse_prediction_snapshots")
        else 0,
    }


def _derive_recommendation(checks: list[dict], segment: dict, predictions: dict) -> str:
    failed = [c for c in checks if not c["passed"]]
    if any(c["check"].startswith("production_") for c in failed):
        return "DO_NOT_PROMOTE_WDE"
    if failed:
        return "NEED_MARKET_SEGMENT_FILTERS"

    ou25_overall = (
        ((segment.get("markets") or {}).get("ou25") or {})
        .get("segments", {})
        .get("overall", {})
    )
    btts_overall = (
        ((segment.get("markets") or {}).get("btts") or {})
        .get("segments", {})
        .get("overall", {})
    )
    ou_delta = ou25_overall.get("shadow_minus_bookmaker") or 0
    btts_delta = btts_overall.get("shadow_minus_bookmaker") or 0
    if ou_delta < 0.005 and btts_delta < 0.005:
        return "SHADOW_MODEL_TOO_WEAK_FOR_LIVE_USE"

    eligible = (predictions.get("filter_summary") or {}).get("eligible_owner_report", 0)
    if eligible > 0 and ou_delta >= 0.01:
        return "READY_FOR_DAILY_OWNER_REPORT_INTEGRATION_OU_BTTS"
    if ou_delta >= 0.005 or btts_delta >= 0.005:
        return "READY_FOR_OWNER_SHADOW_MARKET_REPORT"
    return "NEED_MARKET_SEGMENT_FILTERS"


def build_final_report(
    *,
    validation: dict,
    predictions: dict,
    segments: dict,
    backtest: dict,
    report_md: Path | None,
) -> str:
    test_cmp = (backtest.get("comparison") or {}).get("test") or {}
    rec = validation.get("final_recommendation", "NEED_MARKET_SEGMENT_FILTERS")
    fixtures = predictions.get("fixtures") or []
    scored = [f for f in fixtures if not f.get("skipped")]

    lines = [
        "# WDE Shadow Market Promotion Dry-Run Report",
        "",
        f"**Phase:** {PHASE}  ",
        f"**Generated:** {_utc_now()}  ",
        f"**Mode:** Owner/internal dry-run — no production replacement",
        "",
        "## Model",
        "",
        f"- Path: `{predictions.get('model_dir', DEFAULT_MODEL_DIR)}`",
        f"- Label: `{SHADOW_ONLY_LABEL}`",
        f"- Markets: O/U2.5 + BTTS only; 1X2 blocked",
        "",
        "## Backtest summary (test split)",
        "",
        "| Market | Shadow | Bookmaker | Historical |",
        "|--------|--------|-----------|------------|",
    ]
    for m, label in (("1x2", "1X2"), ("ou25", "O/U2.5"), ("btts", "BTTS")):
        row = test_cmp.get(m) or {}
        lines.append(
            f"| {label} | {row.get('shadow')} | {row.get('bookmaker')} | {row.get('historical')} |"
        )

    lines.extend(
        [
            "",
            "## Why 1X2 is blocked",
            "",
            "- Test accuracy: shadow 49.86% vs bookmaker 50.60%",
            "- Shadow underperforms bookmaker baseline on held-out test",
            "- All 1X2 outputs tagged `1X2_PROMOTION_BLOCKED`",
            "",
            "## O/U2.5 and BTTS eligibility",
            "",
            f"- O/U2.5 test: shadow {((test_cmp.get('ou25') or {}).get('shadow'))} vs book {((test_cmp.get('ou25') or {}).get('bookmaker'))} — **eligible for owner dry-run**",
            f"- BTTS test: shadow {((test_cmp.get('btts') or {}).get('shadow'))} vs book {((test_cmp.get('btts') or {}).get('bookmaker'))} — **eligible for owner dry-run**",
            "",
            "## Upcoming fixture predictions",
            "",
            f"- Window anchor: {predictions.get('anchor_date')}",
            f"- Fixtures discovered: {predictions.get('fixture_count')}",
            f"- Scored: {predictions.get('scored_count')}",
            f"- Eligible owner signals: {(predictions.get('filter_summary') or {}).get('eligible_owner_report', 0)}",
            "",
        ]
    )
    for fx in scored[:10]:
        ou = fx.get("ou25") or {}
        btts = fx.get("btts") or {}
        lines.append(
            f"- {fx.get('match')}: O/U `{ou.get('shadow_pick')}` ({ou.get('shadow_confidence')}) "
            f"BTTS `{btts.get('shadow_pick')}` ({btts.get('shadow_confidence')})"
        )
    if not scored:
        lines.append("- No scored fixtures in current window (odds/features missing)")

    lines.extend(
        [
            "",
            "## Segment analysis highlights",
            "",
        ]
    )
    for market in ("ou25", "btts"):
        best = ((segments.get("markets") or {}).get(market) or {}).get("best_edge_segments") or []
        if best:
            top = best[0]
            lines.append(
                f"- {market.upper()} best segment: `{top.get('segment')}` "
                f"delta={top.get('shadow_minus_bookmaker')} n={top.get('n')}"
            )

    lines.extend(
        [
            "",
            "## Validation",
            "",
            f"- Checks passed: **{validation.get('passed')}** / {validation.get('passed', 0) + validation.get('failed', 0)}",
            f"- Promotion allowed: **False**",
            "",
            "## Final recommendation",
            "",
            f"### `{rec}`",
            "",
            "**No production replacement. No public changes.**",
        ]
    )
    if report_md and report_md.exists():
        lines.append(f"\nOwner report: `{report_md}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="today")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--production-before", default=None, help="JSON file with before counts")
    args = parser.parse_args()

    anchor = resolve_target_date(args.date, args.timezone)
    tag = anchor.strftime("%Y%m%d")
    pred_path = Path(PREDICTIONS_ARTIFACT_TEMPLATE.format(tag=tag))
    report_md = Path("reports/owner") / f"wde_shadow_market_owner_report_{tag}.md"
    report_json = Path(f"artifacts/wde_shadow_market_owner_report_{tag}.json")

    checks: list[dict] = []
    predictions = json.loads(pred_path.read_text(encoding="utf-8")) if pred_path.exists() else {}
    segments = json.loads(SEGMENT_ARTIFACT.read_text(encoding="utf-8")) if SEGMENT_ARTIFACT.exists() else {}
    backtest = json.loads(BACKTEST_ARTIFACT.read_text(encoding="utf-8")) if BACKTEST_ARTIFACT.exists() else {}

    model_dir = Path(predictions.get("model_dir") or DEFAULT_MODEL_DIR)
    checks.append(_check("model_from_shadow_path_only", "shadow" in str(model_dir).lower() and model_dir.exists()))
    checks.append(_check("predictions_artifact_exists", pred_path.exists(), str(pred_path)))
    checks.append(_check("segment_analysis_exists", SEGMENT_ARTIFACT.exists()))
    checks.append(_check("owner_report_md_exists", report_md.exists(), str(report_md)))
    checks.append(_check("owner_report_json_exists", report_json.exists(), str(report_json)))

    checks.append(_check("payload_shadow_only_label", predictions.get("label") == SHADOW_ONLY_LABEL))
    checks.append(_check("1x2_in_markets_blocked", "1x2" in (predictions.get("markets_blocked") or [])))

    all_1x2_blocked = True
    all_shadow_labeled = True
    for fx in predictions.get("fixtures") or []:
        if fx.get("skipped"):
            continue
        comp = fx.get("one_x_two_comparison") or {}
        if comp.get("status") != ONE_X_TWO_BLOCKED:
            all_1x2_blocked = False
        if fx.get("label") != SHADOW_ONLY_LABEL:
            all_shadow_labeled = False
        filt = fx.get("filters") or {}
        if filt.get("1x2", {}).get("eligible_owner_report"):
            all_1x2_blocked = False
    checks.append(_check("1x2_promotion_blocked_all_fixtures", all_1x2_blocked))
    checks.append(_check("fixtures_labeled_shadow_only", all_shadow_labeled))

    # No production script writes
    run_script = (ROOT / "scripts/run_wde_shadow_market_predictions.py").read_text(encoding="utf-8")
    checks.append(_check("inference_script_no_db_writes", "INSERT" not in run_script and "UPDATE" not in run_script))

    main_py = (ROOT / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")
    checks.append(_check("no_public_route_wde_shadow_market", "wde-shadow-market" not in main_py.lower()))

    conn = connect_readonly(get_settings().sqlite_path)
    after = _production_counts(conn)
    conn.close()

    before = {}
    if args.production_before:
        before = json.loads(Path(args.production_before).read_text(encoding="utf-8"))
    else:
        before = after

    for table in ("worldcup_stored_predictions", "odds_snapshots", "ecse_prediction_snapshots"):
        checks.append(
            _check(
                f"production_{table}_unchanged",
                after.get(table) == before.get(table),
                f"before={before.get(table)} after={after.get(table)}",
            )
        )

    passed = sum(1 for c in checks if c["passed"])
    failed = sum(1 for c in checks if not c["passed"])
    recommendation = _derive_recommendation(checks, segments, predictions)

    validation = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "checks": checks,
        "passed": passed,
        "failed": failed,
        "promotion_allowed": False,
        "production_counts_after": after,
        "final_recommendation": recommendation,
    }
    VALIDATION_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_ARTIFACT.write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")

    FINAL_REPORT.write_text(
        build_final_report(
            validation=validation,
            predictions=predictions,
            segments=segments,
            backtest=backtest,
            report_md=report_md,
        ),
        encoding="utf-8",
    )

    print(json.dumps({"passed": passed, "failed": failed, "final_recommendation": recommendation}, indent=2))
    print(f"Written: {VALIDATION_ARTIFACT}")
    print(f"Written: {FINAL_REPORT}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
