"""Owner-scope discovery with explicit exclusion reasons."""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import Any

from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.gpt_actions.competition_normalize import normalize_competition_key
from worldcup_predictor.gpt_actions.delegation import discover_today_matches
from worldcup_predictor.gpt_actions.owner_scope import fixture_tier
from worldcup_predictor.gpt_actions.tier_b_shadow_registry import TIER_B_SHADOW_DOMAINS
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot
from worldcup_predictor.odds.freshness_policy import FreshnessStatus
from worldcup_predictor.research.ecse_timing_experiment.constants import FRIENDLY_KEYS, PREMATCH, STARTED, TZ_NAME
from worldcup_predictor.research.ecse_timing_experiment.extract import odds_blob
from worldcup_predictor.research.ecse_timing_experiment.windows import to_vienna

FRESH_OK = frozenset({FreshnessStatus.FRESH_ODDS.value, "fresh", "ODDS_FRESH", "FRESH_ODDS"})


def _league_country(competition: str | None) -> tuple[str, str]:
    canon = normalize_competition_key(competition) or str(competition or "unknown")
    try:
        comp = get_competition(canon)
        return comp.name, comp.country or "International"
    except Exception:
        meta = TIER_B_SHADOW_DOMAINS.get(canon) or {}
        return meta.get("name") or canon.replace("_", " ").title(), str(meta.get("country") or "UNKNOWN")


def _fresh_ok(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, dict):
        for key in ("freshness_flag", "odds_freshness_status", "policy_status", "freshness_class", "freshness_status"):
            if _fresh_ok(v.get(key)):
                return True
        return False
    t = str(v).strip()
    return t in FRESH_OK or ("fresh" in t.lower() and "stale" not in t.lower())


def discover_owner_day(
    *,
    target_date: str,
    timezone: str = TZ_NAME,
    prod_conn: Any,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Discover owner Tier A/B fixtures for a Vienna calendar day with explicit exclusions."""
    now = as_of or datetime.now(dt_timezone.utc)
    raw = discover_today_matches(target_date=target_date, timezone=timezone, scope="owner")
    matches = list(raw.get("matches") or [])
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for m in matches:
        fid = int(m.get("fixture_id") or 0)
        comp = normalize_competition_key(m.get("competition") or m.get("competition_key") or "") or ""
        league, country = _league_country(comp)
        status = str(m.get("status") or "NS").upper()
        kickoff = str(m.get("kickoff_utc") or m.get("kickoff") or "")
        tier = m.get("validation_tier") or fixture_tier(comp)
        pred_scope = "production" if str(tier).upper() == "A" else "owner_shadow"
        base = {
            "fixture_id": fid,
            "home_team": m.get("home_team") or m.get("home"),
            "away_team": m.get("away_team") or m.get("away"),
            "league": league,
            "country": country,
            "competition_key": comp,
            "kickoff_utc": kickoff,
            "kickoff_vienna": to_vienna(kickoff, timezone),
            "tier": tier,
            "prediction_scope": pred_scope,
            "status": status,
            "source": m.get("source") or m.get("provider") or "owner_discovery",
        }

        if not fid:
            excluded.append({**base, "discovery_status": "EXCLUDED", "exclusion_reason": "BLOCKED_UNSUPPORTED_FIXTURE:missing_id"})
            continue
        if comp in FRIENDLY_KEYS or str(m.get("listing_status") or "").upper() == "FRIENDLY":
            excluded.append({**base, "discovery_status": "EXCLUDED", "exclusion_reason": "BLOCKED_UNSUPPORTED_FIXTURE:friendly"})
            continue
        if str(m.get("prediction_support_status") or "").upper() in {"FRIENDLY", "NO_PREDICTION_SUPPORT", "UNSUPPORTED"}:
            excluded.append(
                {
                    **base,
                    "discovery_status": "EXCLUDED",
                    "exclusion_reason": f"BLOCKED_UNSUPPORTED_FIXTURE:{m.get('prediction_support_status')}",
                }
            )
            continue
        if str(tier).upper() not in {"A", "B"}:
            excluded.append({**base, "discovery_status": "EXCLUDED", "exclusion_reason": "BLOCKED_UNSUPPORTED_FIXTURE:non_owner_tier"})
            continue
        if status in STARTED:
            excluded.append({**base, "discovery_status": "EXCLUDED", "exclusion_reason": "BLOCKED_FIXTURE_STARTED"})
            continue
        if status not in PREMATCH:
            # Finished or cancelled for "tomorrow" discovery — still record
            excluded.append(
                {
                    **base,
                    "discovery_status": "EXCLUDED",
                    "exclusion_reason": f"BLOCKED_FIXTURE_STARTED:status={status}",
                }
            )
            continue

        snap = get_latest_valid_1x2_odds_snapshot(prod_conn, fid, kickoff_utc=kickoff)
        odds = odds_blob(snap)
        base["provider"] = odds.get("provider") or base["source"]
        base["bookmaker_count"] = odds.get("bookmaker_count")
        base["latest_odds_timestamp"] = odds.get("fetched_at")
        base["odds"] = odds

        h, d, a = odds.get("home"), odds.get("draw"), odds.get("away")
        if not (h and d and a and h > 1 and d > 1 and a > 1):
            excluded.append(
                {
                    **base,
                    "discovery_status": "EXCLUDED",
                    "exclusion_reason": "BLOCKED_INCOMPLETE_ODDS",
                }
            )
            continue
        if not _fresh_ok(odds.get("freshness_status")):
            # Discovery may still include for later refresh attempt; mark soft exclude for capture gate
            excluded.append(
                {
                    **base,
                    "discovery_status": "EXCLUDED",
                    "exclusion_reason": "BLOCKED_STALE_ODDS",
                }
            )
            continue

        included.append({**base, "discovery_status": "INCLUDED", "exclusion_reason": None})

    return {
        "target_date": target_date,
        "timezone": timezone,
        "as_of_utc": now.isoformat(),
        "discovery_raw_count": len(matches),
        "included": included,
        "excluded": excluded,
        "included_count": len(included),
        "excluded_count": len(excluded),
        "audit": raw.get("audit"),
        "tier_a_count": sum(1 for x in included if str(x.get("tier")).upper() == "A"),
        "tier_b_count": sum(1 for x in included if str(x.get("tier")).upper() == "B"),
    }
