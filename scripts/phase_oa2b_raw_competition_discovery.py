#!/usr/bin/env python3
"""PHASE OA-2B — Raw OddAlerts competition discovery audit."""

from __future__ import annotations

import json
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

    from worldcup_predictor.egie.oddalerts_audit.raw_competition_discovery import run_audit
    from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient

    client = OddAlertsClient()
    if not client.is_configured:
        print("ERROR: ODDALERTS_API_KEY not set")
        return 1

    inventory = run_audit(client=client)
    scope = inventory.get("subscription_scope") or {}
    print(
        "Done: catalogue=%s pool_comps=%s finished_fixtures=%s api_calls=%s"
        % (
            scope.get("competitions_catalogue_total"),
            scope.get("competitions_with_any_pool_fixtures"),
            scope.get("unique_finished_fixtures_in_results_pool"),
            (inventory.get("api_stats") or {}).get("api_calls"),
        )
    )
    if "--json" in sys.argv:
        print(json.dumps(scope, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
