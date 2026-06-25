#!/usr/bin/env python3
"""Phase 31B — historical replay backtest validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"
SUMMARY = ARTIFACTS / "backtest_ranked_picks_summary.json"
CSV = ARTIFACTS / "backtest_ranked_picks_full.csv"
REPORT = ROOT / "PHASE_31B_HISTORICAL_REPLAY_BACKTEST_REPORT.md"


def _assert(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name}" + (f" — {detail}" if detail else ""))
        raise AssertionError(name)


def main() -> None:
    _assert("summary JSON exists", SUMMARY.is_file())
    _assert("CSV exists", CSV.is_file())
    _assert("report exists", REPORT.is_file())

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    meta = summary.get("meta") or {}
    _assert("finished matches replayed", int(meta.get("replayed_ok") or 0) > 0)
    _assert("threshold matrix present", bool(summary.get("threshold_matrix")))
    for t in ("50", "55", "60"):
        row = summary["threshold_matrix"].get(t)
        _assert(f"threshold {t} executed", row is not None)
        _assert(f"threshold {t} no_bet_rate", row.get("no_bet_rate") is not None)
        _assert(f"threshold {t} recommendation_rate", row.get("recommendation_rate") is not None)
        _assert(f"threshold {t} winrate fields", "ranked_picks" in row and "markets" in row)

    _assert("confidence bucket analysis", bool(summary.get("confidence_bucket_analysis")))
    buckets = summary["confidence_bucket_analysis"]
    _assert(
        "confidence buckets populated",
        any(v.get("count", 0) > 0 for v in buckets.values()),
        "no bucket counts",
    )

    rp = summary["threshold_matrix"]["60"]["ranked_picks"]
    _assert("safe pick stats", "safe_pick" in rp)
    _assert("value pick stats", "value_pick" in rp)
    _assert("aggressive pick stats", "aggressive_pick" in rp)

    csv_lines = CSV.read_text(encoding="utf-8").strip().splitlines()
    _assert("CSV has rows", len(csv_lines) > 1, f"lines={len(csv_lines)}")

    print("\nAll Phase 31B validation checks passed.")


if __name__ == "__main__":
    main()
