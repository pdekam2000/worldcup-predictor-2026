#!/usr/bin/env python3
"""PHASE OA-4 — Documented endpoint traversal (Postman params)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    from worldcup_predictor.egie.oddalerts_audit.oa4_documented_traversal import run_documented_audit
    from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient

    client = OddAlertsClient()
    if not client.is_configured:
        print("ERROR: ODDALERTS_API_KEY not configured")
        return 1

    doc = run_documented_audit(client=client)
    print("OA-4 documented audit complete: api_calls=%s" % doc.get("api_calls"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
