#!/usr/bin/env python3
"""PHASE WDE-SHADOW-3 Part D — Owner report for WDE shadow O/U2.5 + BTTS dry-run."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_daily.fixture_discovery import resolve_target_date
from worldcup_predictor.owner_daily.constants import DEFAULT_TIMEZONE, REPORTS_DIR
from worldcup_predictor.research.wde_shadow_market_inference import PREDICTIONS_ARTIFACT_TEMPLATE

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PHASE = "WDE-SHADOW-3"
SEGMENT_ARTIFACT = Path("artifacts/wde_shadow_market_segment_analysis.json")
BACKTEST_ARTIFACT = Path("artifacts/wde_shadow_vs_current_backtest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _date_tag(d) -> str:
    return d.strftime("%Y%m%d")


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _best_signals(fixtures: list[dict], market: str, badge: str, limit: int = 15) -> list[dict]:
    out = []
    for fx in fixtures:
        if fx.get("skipped"):
            continue
        filt = (fx.get("filters") or {}).get(market) or {}
        if filt.get("signal_badge") != badge:
            continue
        mkt = fx.get(market) or {}
        out.append(
            {
                "fixture_id": fx.get("fixture_id"),
                "match": fx.get("match"),
                "competition": fx.get("competition"),
                "kickoff": fx.get("kickoff"),
                "shadow_pick": mkt.get("shadow_pick"),
                "shadow_confidence": mkt.get("shadow_confidence"),
                "bookmaker_pick": mkt.get("bookmaker_pick"),
                "production_wde_pick": mkt.get("production_wde_pick"),
                "reasons": filt.get("reasons"),
            }
        )
    out.sort(key=lambda x: -(float(x.get("shadow_confidence") or 0)))
    return out[:limit]


def build_report_payload(predictions: dict, segments: dict, backtest: dict) -> dict:
    fixtures = predictions.get("fixtures") or []
    disagreements = [
        {
            "fixture_id": f.get("fixture_id"),
            "match": f.get("match"),
            "flags": f.get("disagreement_flags"),
            "ou25": (f.get("ou25") or {}).get("shadow_pick"),
            "btts": (f.get("btts") or {}).get("shadow_pick"),
        }
        for f in fixtures
        if f.get("disagreement_flags")
    ]
    do_not_use = [
        {
            "fixture_id": f.get("fixture_id"),
            "match": f.get("match"),
            "ou25_badge": (f.get("filters") or {}).get("ou25", {}).get("signal_badge"),
            "btts_badge": (f.get("filters") or {}).get("btts", {}).get("signal_badge"),
        }
        for f in fixtures
        if not f.get("eligible_owner_report") and not f.get("skipped")
    ]
    missing = [f for f in fixtures if f.get("skipped") or f.get("missing_features")]

    test_cmp = (backtest.get("comparison") or {}).get("test") or {}

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "label": "SHADOW_ONLY",
        "model_dir": predictions.get("model_dir"),
        "model_status": {
            "mode": "SHADOW_ONLY",
            "markets_enabled": ["ou25", "btts"],
            "markets_blocked": ["1x2"],
            "1x2_blocked_reason": "shadow underperformed bookmaker baseline on test",
        },
        "backtest_test_summary": test_cmp,
        "best_ou25_signals": {
            "strong": _best_signals(fixtures, "ou25", "STRONG_SHADOW_OU25"),
            "medium": _best_signals(fixtures, "ou25", "MEDIUM_SHADOW_OU25"),
        },
        "best_btts_signals": {
            "strong": _best_signals(fixtures, "btts", "STRONG_SHADOW_BTTS"),
            "medium": _best_signals(fixtures, "btts", "MEDIUM_SHADOW_BTTS"),
        },
        "disagreements": disagreements[:25],
        "do_not_use_signals": do_not_use[:25],
        "missing_data": missing[:25],
        "filter_summary": predictions.get("filter_summary"),
        "segment_highlights": {
            "ou25_best": ((segments.get("markets") or {}).get("ou25") or {}).get("best_edge_segments", [])[:5],
            "ou25_avoid": ((segments.get("markets") or {}).get("ou25") or {}).get("avoid_segments", [])[:5],
            "btts_best": ((segments.get("markets") or {}).get("btts") or {}).get("best_edge_segments", [])[:5],
            "btts_avoid": ((segments.get("markets") or {}).get("btts") or {}).get("avoid_segments", [])[:5],
        },
        "predictions_artifact": predictions.get("artifact_path"),
    }


def build_markdown(payload: dict) -> str:
    ms = payload.get("model_status") or {}
    bt = payload.get("backtest_test_summary") or {}
    fs = payload.get("filter_summary") or {}

    def _fmt_market(m: str) -> str:
        row = bt.get(m) or {}
        return f"shadow={row.get('shadow')} book={row.get('bookmaker')} hist={row.get('historical')}"

    lines = [
        "# WDE Shadow Market Owner Report",
        "",
        f"**Phase:** {PHASE}  ",
        f"**Generated:** {payload.get('generated_at_utc')}  ",
        f"**Label:** `{payload.get('label')}`",
        "",
        "## 1. Model status",
        "",
        f"- Mode: **{ms.get('mode')}**",
        f"- Markets enabled: **{', '.join(ms.get('markets_enabled') or [])}**",
        f"- Markets blocked: **{', '.join(ms.get('markets_blocked') or [])}**",
        f"- 1X2 blocked: {ms.get('1x2_blocked_reason')}",
        f"- Model path: `{payload.get('model_dir')}`",
        "",
        "## 2. Backtest summary (test split)",
        "",
        f"- O/U2.5: {_fmt_market('ou25')}",
        f"- BTTS: {_fmt_market('btts')}",
        f"- 1X2 (blocked): {_fmt_market('1x2')}",
        "",
        "## 3. Best O/U2.5 signals",
        "",
    ]
    for item in (payload.get("best_ou25_signals") or {}).get("strong") or []:
        lines.append(
            f"- **{item.get('match')}** — pick `{item.get('shadow_pick')}` "
            f"conf={item.get('shadow_confidence')} (book: {item.get('bookmaker_pick')})"
        )
    if not (payload.get("best_ou25_signals") or {}).get("strong"):
        lines.append("- No STRONG O/U2.5 signals in current window")

    lines.extend(["", "## 4. Best BTTS signals", ""])
    for item in (payload.get("best_btts_signals") or {}).get("strong") or []:
        lines.append(
            f"- **{item.get('match')}** — pick `{item.get('shadow_pick')}` "
            f"conf={item.get('shadow_confidence')} (book: {item.get('bookmaker_pick')})"
        )
    if not (payload.get("best_btts_signals") or {}).get("strong"):
        lines.append("- No STRONG BTTS signals in current window")

    lines.extend(["", "## 5. Disagreements", ""])
    for d in payload.get("disagreements") or []:
        lines.append(f"- {d.get('match')}: {', '.join(d.get('flags') or [])}")
    if not payload.get("disagreements"):
        lines.append("- None in current window")

    lines.extend(["", "## 6. Do-not-use signals", ""])
    for d in payload.get("do_not_use_signals") or []:
        lines.append(f"- {d.get('match')}: ou25={d.get('ou25_badge')} btts={d.get('btts_badge')}")

    lines.extend(["", "## 7. Missing data / skipped", ""])
    for m in payload.get("missing_data") or []:
        lines.append(f"- {m.get('match')}: {m.get('missing_features')}")

    lines.extend(
        [
            "",
            "## Filter summary",
            "",
            f"- Fixtures: {fs.get('total_fixtures')}",
            f"- Eligible for owner report: {fs.get('eligible_owner_report')}",
            f"- 1X2 always blocked: {fs.get('1x2_always_blocked')}",
            "",
            "**Owner/internal only. No production WDE replacement. No public changes.**",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="today")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    args = parser.parse_args()

    anchor = resolve_target_date(args.date, args.timezone)
    tag = _date_tag(anchor)
    pred_path = Path(PREDICTIONS_ARTIFACT_TEMPLATE.format(tag=tag))
    predictions = _load_json(pred_path)
    if not predictions:
        print(f"Missing predictions artifact: {pred_path}", file=sys.stderr)
        return 1
    predictions["artifact_path"] = str(pred_path)

    segments = _load_json(SEGMENT_ARTIFACT)
    backtest = _load_json(BACKTEST_ARTIFACT)
    payload = build_report_payload(predictions, segments, backtest)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORTS_DIR / f"wde_shadow_market_owner_report_{tag}.md"
    json_path = Path(f"artifacts/wde_shadow_market_owner_report_{tag}.json")
    md_path.write_text(build_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"markdown": str(md_path), "json": str(json_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
