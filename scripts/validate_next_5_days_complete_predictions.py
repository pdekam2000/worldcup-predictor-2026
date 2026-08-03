#!/usr/bin/env python3
"""Validate NEXT_5_DAYS_COMPLETE_FRESH_ODDS_PREDICTION_AND_LISTING artifacts."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Europe/Vienna")


def latest_art() -> Path | None:
    base = ROOT / "artifacts" / "next_5_days_complete_predictions"
    if not base.exists():
        return None
    runs = sorted(base.glob("*/*"), key=lambda p: p.stat().st_mtime if p.is_dir() else 0, reverse=True)
    for r in runs:
        if (r / "validation_report.json").exists():
            return r
    return None


def main() -> int:
    art = latest_art()
    checks: list[tuple[str, bool, str]] = []

    def chk(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        print(("PASS" if ok else "FAIL"), name, detail)

    if art is None:
        print("FAIL no_artifacts")
        return 1

    dates_meta = json.loads((art / "resolved_dates.json").read_text(encoding="utf-8"))
    val = json.loads((art / "validation_report.json").read_text(encoding="utf-8"))
    today = datetime.now(TZ).date()
    expected = [(today + timedelta(days=i)).isoformat() for i in range(5)]
    chk("1_five_vienna_dates", dates_meta.get("dates") == expected, str(dates_meta.get("dates")))
    chk("2_timezone", dates_meta.get("timezone") == "Europe/Vienna")
    required = [
        "run_manifest.json",
        "discovered_universe.json",
        "supported_fixtures.json",
        "blocked_fixtures.json",
        "canonical_predictions.json",
        "complete_predictions.csv",
        "ecse_top10_all_fixtures.csv",
        "ranked_1x2_candidates.json",
        "ranked_exact_score_candidates.json",
        "full_owner_table_fa.csv",
        "freeze_integrity_report.json",
        "true_forward_collection_report.json",
        "NEXT_5_DAYS_COMPLETE_PREDICTION_REPORT.md",
        "NEXT_5_DAYS_COMPLETE_PREDICTION_REPORT_FA.md",
        "owner_next_5_days_dashboard.html",
    ]
    for name in required:
        chk(f"artifact_{name}", (art / name).exists())
    chk("canonical_unchanged", val.get("canonical_unchanged") is True)
    chk("wde_unchanged", val.get("wde_unchanged") is True)
    chk("ecse_unchanged", val.get("ecse_unchanged") is True)
    chk("no_auto_promotion", val.get("no_auto_promotion") is True)
    chk("no_routing", val.get("no_routing_activation") is True)
    chk("status_ok", str(val.get("status") or "").startswith("NEXT_5_DAYS"))
    canon = json.loads((art / "canonical_predictions.json").read_text(encoding="utf-8"))
    preds = canon.get("predictions") or []
    if preds:
        e = (preds[0].get("ecse") or {})
        chk("top10_present_when_complete", bool(e.get("top1")) or bool(e.get("top10")))
    fa = (art / "NEXT_5_DAYS_COMPLETE_PREDICTION_REPORT_FA.md").read_text(encoding="utf-8")
    chk("fa_has_predictions", "vs" in fa or "Top1" in fa)
    failed = [c for c in checks if not c[1]]
    print(f"RESULT {len(checks)-len(failed)}/{len(checks)} passed · art={art}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
