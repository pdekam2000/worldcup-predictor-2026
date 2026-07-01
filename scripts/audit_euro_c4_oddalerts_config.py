#!/usr/bin/env python3
"""PHASE EURO-C4 Part A — OddAlerts config and endpoint audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.owner.euro_c4_oddalerts import CONFIG_AUDIT_PATH, audit_oddalerts_config

DEFAULT_OUT = ROOT / "artifacts" / "euro_c4_oddalerts_config_audit.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    audit = audit_oddalerts_config(settings=get_settings())
    out = Path(CONFIG_AUDIT_PATH)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OddAlerts token configured: {audit.get('token_configured')}")
    print(f"Base URL: {audit.get('base_url')}")
    print(f"EURO-C3 zero-call reasons: {len(audit.get('euro_c3_oddalerts_calls_zero_reasons') or [])}")
    print(f"Written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
