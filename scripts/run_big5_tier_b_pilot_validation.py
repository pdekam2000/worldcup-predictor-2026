#!/usr/bin/env python3
"""Big 5 Tier B onboarding evidence collection."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ART = ROOT / "artifacts" / "big5_european_league_audit"
ART.mkdir(parents=True, exist_ok=True)

PILOT_DATE = "2026-08-22"
ONBOARDED = ("la_liga", "serie_a", "ligue_1")
TIER_A = ("premier_league", "bundesliga")


def main() -> int:
    from worldcup_predictor.gpt_actions.broad_fixture_discovery import discover_broad_fixtures
    from worldcup_predictor.gpt_actions.competition_normalize import normalize_competition_key
    from worldcup_predictor.gpt_actions.delegation import discover_today_matches
    from worldcup_predictor.gpt_actions.owner_scope import competition_keys_for_scope, fixture_tier
    from worldcup_predictor.gpt_actions.tier_b_shadow_registry import TIER_B_SHADOW_DOMAINS, get_tier_b_domain
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS

    settings = get_settings()
    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "pilot_date": PILOT_DATE,
        "tier_b_count": len(TIER_B_SHADOW_DOMAINS),
        "onboarded": {},
        "tier_a_preserved": {},
    }

    broad = discover_broad_fixtures(
        target_date=PILOT_DATE, timezone="Europe/Vienna", settings=settings, sync_prediction_candidates=True
    )
    owner = discover_today_matches(target_date=PILOT_DATE, timezone="Europe/Vienna", scope="owner")
    prod = discover_today_matches(target_date=PILOT_DATE, timezone="Europe/Vienna", scope="production")
    shadow = discover_today_matches(target_date=PILOT_DATE, timezone="Europe/Vienna", scope="shadow")

    owner_keys = competition_keys_for_scope("owner")
    prod_keys = competition_keys_for_scope("production")

    for key in ONBOARDED:
        meta = get_tier_b_domain(key)
        rows = [
            m
            for m in broad.get("matches") or []
            if normalize_competition_key(str(m.get("competition") or m.get("competition_raw") or "")) == key
        ]
        out["onboarded"][key] = {
            "registered": meta is not None,
            "provider_league_id": int(meta["provider_league_id"]) if meta else None,
            "tier": fixture_tier(key),
            "owner_scope": key in owner_keys,
            "production_excluded": key not in prod_keys,
            "broad_count": len(rows),
            "broad_sample": rows[:2],
            "owner_discover": [m for m in owner.get("matches") or [] if m.get("competition") == key],
            "production_discover": [m for m in prod.get("matches") or [] if m.get("competition") == key],
        }

    for key in TIER_A:
        out["tier_a_preserved"][key] = {
            "tier_a": key in DAILY_SUPPORTED_COMPETITIONS,
            "tier_b_duplicate": get_tier_b_domain(key) is not None,
            "production_scope": key in prod_keys,
            "fixture_tier": fixture_tier(key),
        }

    out["discover_counts"] = {
        "owner": owner.get("count"),
        "production": prod.get("count"),
        "shadow": shadow.get("count"),
        "tier_b": owner.get("tier_b_count"),
    }
    path = ART / "onboarding_evidence.json"
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"status": "ok", "path": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
