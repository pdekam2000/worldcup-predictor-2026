#!/usr/bin/env python3
"""PHASE OA-4 — Deep OddAlerts endpoint traversal audit."""

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

    from worldcup_predictor.egie.oddalerts_audit.oa4_endpoint_traversal import run_oa4_traversal
    from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient

    client = OddAlertsClient()
    if not client.is_configured:
        print("ERROR: ODDALERTS_API_KEY not configured")
        return 1

    proof = run_oa4_traversal(client=client)
    stats = proof.get("api_stats") or {}
    inv = proof.get("inventory") or []
    finished_rows = sum(1 for r in inv if (r.get("finished_fixture_count") or 0) > 0)
    upcoming_rows = sum(1 for r in inv if (r.get("upcoming_fixture_count") or 0) > 0)
    print(
        "OA-4 complete: api_calls=%s attempts=%s inventory_rows=%s finished_gt0=%s upcoming_gt0=%s"
        % (stats.get("api_calls"), stats.get("endpoint_attempts"), len(inv), finished_rows, upcoming_rows)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
