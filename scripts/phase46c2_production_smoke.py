#!/usr/bin/env python3
"""Phase 46C-2 production smoke — verify advanced market evaluations."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    repo = FootballIntelligenceRepository(get_settings().sqlite_path)
    rows = [r for r in repo.list_worldcup_prediction_evaluations() if r.get("final_score")]
    print(f"evaluations_with_score={len(rows)}")
    advanced_rows = 0
    for row in rows:
        has_adv = any(row.get(c) for c in (
            "market_ht_status", "market_cs_status", "market_fg_team_status", "market_goalscorer_status"
        ))
        detail = {}
        try:
            detail = json.loads(row.get("detail_json") or "{}")
        except json.JSONDecodeError:
            pass
        adv = detail.get("advanced_markets") or {}
        if adv or has_adv:
            advanced_rows += 1
        print(
            f"fixture={row['fixture_id']} ht={row.get('market_ht_status')} "
            f"cs={row.get('market_cs_status')} fg={row.get('market_fg_team_status')} "
            f"gs={row.get('market_goalscorer_status')}"
        )
        for key, block in adv.items():
            if isinstance(block, dict):
                print(f"  {key}: status={block.get('status')} pred={block.get('predicted')} actual={block.get('actual')}")
    print(f"advanced_evaluated_rows={advanced_rows}")
    return 0 if advanced_rows > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
