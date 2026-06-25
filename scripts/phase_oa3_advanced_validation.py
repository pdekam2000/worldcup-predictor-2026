#!/usr/bin/env python3
"""PHASE OA-3 — OddAlerts Advanced plan deep validation audit."""

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

    from worldcup_predictor.egie.oddalerts_audit.oa3_advanced_audit import run_oa3_audit
    from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient

    client = OddAlertsClient()
    if not client.is_configured:
        print("ERROR: ODDALERTS_API_KEY not configured")
        return 1

    result = run_oa3_audit(client=client)
    print("OA-3 complete: api_calls=%s artifacts=%s" % (result["stats"]["api_calls"], len(result["artifacts"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
