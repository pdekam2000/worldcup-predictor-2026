#!/usr/bin/env python3
"""Preview OddAlerts policy selections as odds snapshot payloads (dry-run)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.data_import.oddalerts_bookmaker_policy import (
    PROCESS_DATE,
    preview_odds_snapshot_payloads,
)

MATRIX = Path(f"artifacts/oddalerts_policy_market_matrix_{PROCESS_DATE.replace('-', '')}.json")
OUT = Path(f"artifacts/oddalerts_policy_odds_snapshot_preview_{PROCESS_DATE.replace('-', '')}.json")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not MATRIX.exists():
        print(f"Missing matrix: {MATRIX}", file=sys.stderr)
        return 2

    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    preview = preview_odds_snapshot_payloads(matrix)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(preview, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({k: preview[k] for k in preview if k != "previews"}, indent=2))
    print(f"Written: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
