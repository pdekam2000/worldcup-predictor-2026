"""Canonical Correct Score market mapping (90-minute regulation only)."""

from __future__ import annotations

import re
from typing import Any

from worldcup_predictor.research.correct_score_odds.statuses import (
    ANY_OTHER_AWAY,
    ANY_OTHER_DRAW,
    ANY_OTHER_HOME,
    CANONICAL_MARKET,
)

SCORE_RE = re.compile(r"^(\d{1,2})\s*[-:]\s*(\d{1,2})$")

# Provider market name → accept / reject for 90-min CS
_ACCEPT_HINTS = (
    "correct score",
    "exact score",
    "full time correct score",
    "ft correct score",
    "90 minute correct score",
    "match correct score",
)

_REJECT_HINTS = (
    "1st half",
    "first half",
    "2nd half",
    "second half",
    "half time",
    "halftime",
    "extra time",
    "aet",
    "penalt",
    "to qualify",
    "match result & correct score",  # combo market — not pure CS
    "result/correct",
    "correct score &",
    "scorecast",
    "wincast",
)

_ANY_OTHER_MAP = {
    "any other home win": ANY_OTHER_HOME,
    "any other home": ANY_OTHER_HOME,
    "other home win": ANY_OTHER_HOME,
    "any other draw": ANY_OTHER_DRAW,
    "other draw": ANY_OTHER_DRAW,
    "any other away win": ANY_OTHER_AWAY,
    "any other away": ANY_OTHER_AWAY,
    "other away win": ANY_OTHER_AWAY,
}


def normalize_market_name(raw: str) -> str | None:
    """Return CANONICAL_MARKET if accepted 90-min CS; None if rejected/unknown."""
    n = (raw or "").lower().strip()
    if not n:
        return None
    if any(h in n for h in _REJECT_HINTS):
        return None
    if any(h in n for h in _ACCEPT_HINTS):
        return CANONICAL_MARKET
    return None


def parse_selection(raw: str) -> dict[str, Any] | None:
    """
    Parse selection to either exact score or any-other bucket.
    Returns dict with keys: selection, home_goals, away_goals, market, is_any_other
    """
    label = (raw or "").strip().replace(":", "-")
    low = label.lower()
    if low in _ANY_OTHER_MAP:
        return {
            "selection": _ANY_OTHER_MAP[low],
            "home_goals": None,
            "away_goals": None,
            "market": _ANY_OTHER_MAP[low],
            "is_any_other": True,
        }
    # fuzzy any-other
    for key, canon in _ANY_OTHER_MAP.items():
        if key in low:
            return {
                "selection": canon,
                "home_goals": None,
                "away_goals": None,
                "market": canon,
                "is_any_other": True,
            }
    m = SCORE_RE.match(label.replace(" ", ""))
    if not m:
        return None
    hg, ag = int(m.group(1)), int(m.group(2))
    if hg > 20 or ag > 20:
        return None
    return {
        "selection": f"{hg}-{ag}",
        "home_goals": hg,
        "away_goals": ag,
        "market": CANONICAL_MARKET,
        "is_any_other": False,
    }


def provider_capability_matrix() -> list[dict[str, Any]]:
    """Static capability matrix from prior audits + code inspection (no live quota burn)."""
    return [
        {
            "provider": "api_football",
            "correct_score_available": "yes",
            "prematch_available": "yes",
            "live_only": "no",
            "historical_available": "partial_via_cached_snapshots",
            "bookmaker_level": "yes",
            "world_cup": "yes_when_quoted",
            "uefa_qualifiers": "yes_when_quoted",
            "domestic_tier_b": "partial",
            "rate_limits": "daily_quota_plan_dependent",
            "quota_cost": "1_call_per_fixture_odds",
            "market_identifier": "bet.name == 'Correct Score'",
            "settlement_scope": "90_MINUTES_assumed_for_Correct_Score_label",
            "update_frequency": "prematch_until_kickoff",
            "historical_retention": "depends_on_local_odds_snapshots_cache",
            "licensing": "api_sports_terms",
            "preferred_order_rank": 1,
            "notes": "Confirmed CS in provider truth audit and local snapshots",
        },
        {
            "provider": "sportmonks",
            "correct_score_available": "yes",
            "prematch_available": "yes",
            "live_only": "no",
            "historical_available": "partial_via_premium_odds_include",
            "bookmaker_level": "yes",
            "world_cup": "yes_when_mapped",
            "uefa_qualifiers": "yes_when_mapped",
            "domestic_tier_b": "partial",
            "rate_limits": "plan_dependent",
            "quota_cost": "premium_odds_include",
            "market_identifier": "market_key correct_score / Correct Score",
            "settlement_scope": "90_MINUTES_when_labelled_Correct_Score",
            "update_frequency": "prematch",
            "historical_retention": "local_snapshots_when_imported",
            "licensing": "sportmonks_terms",
            "preferred_order_rank": 2,
            "notes": "CS present when premium odds available; UEFA dump historically sparse",
        },
        {
            "provider": "oddalerts",
            "correct_score_available": "no",
            "prematch_available": "n/a",
            "live_only": "n/a",
            "historical_available": "no",
            "bookmaker_level": "n/a",
            "world_cup": "mapping_often_missing",
            "uefa_qualifiers": "unknown",
            "domestic_tier_b": "unknown",
            "rate_limits": "api_plan",
            "quota_cost": "n/a_for_cs",
            "market_identifier": "none_in_history_csv",
            "settlement_scope": "n/a",
            "update_frequency": "n/a",
            "historical_retention": "csv_has_zero_cs_rows",
            "licensing": "oddalerts_terms",
            "preferred_order_rank": 99,
            "notes": "OA1 audit: correct score market in history = False",
        },
        {
            "provider": "the_odds_api",
            "correct_score_available": "no",
            "prematch_available": "h2h_totals_only",
            "live_only": "no",
            "historical_available": "no_for_cs",
            "bookmaker_level": "yes_for_h2h",
            "world_cup": "partial",
            "uefa_qualifiers": "partial",
            "domestic_tier_b": "partial",
            "rate_limits": "monthly_credit_budget",
            "quota_cost": "credits_per_market",
            "market_identifier": "DEFAULT_MARKETS=h2h,totals — CS not configured",
            "settlement_scope": "n/a",
            "update_frequency": "n/a",
            "historical_retention": "n/a",
            "licensing": "the_odds_api_terms",
            "preferred_order_rank": 99,
            "notes": "Do not expand markets without credit budget approval",
        },
        {
            "provider": "historical_csv_odds",
            "correct_score_available": "no",
            "prematch_available": "1x2_ou_btts_only",
            "live_only": "no",
            "historical_available": "no_cs",
            "bookmaker_level": "yes_for_non_cs",
            "world_cup": "n/a",
            "uefa_qualifiers": "n/a",
            "domestic_tier_b": "n/a",
            "rate_limits": "n/a",
            "quota_cost": "0",
            "market_identifier": "none",
            "settlement_scope": "n/a",
            "update_frequency": "n/a",
            "historical_retention": "large_but_no_cs",
            "licensing": "source_csv_terms",
            "preferred_order_rank": 99,
            "notes": "Zero reliable Correct Score rows in clean imports",
        },
        {
            "provider": "manual_owner_import",
            "correct_score_available": "yes_with_confirmation",
            "prematch_available": "yes",
            "live_only": "no",
            "historical_available": "owner_provided_only",
            "bookmaker_level": "yes",
            "world_cup": "yes",
            "uefa_qualifiers": "yes",
            "domestic_tier_b": "yes",
            "rate_limits": "n/a",
            "quota_cost": "0",
            "market_identifier": "owner_transcribed",
            "settlement_scope": "must_be_confirmed_90_MINUTES",
            "update_frequency": "manual",
            "historical_retention": "retained_with_image_provenance",
            "licensing": "owner_responsibility",
            "preferred_order_rank": 3,
            "notes": "Never presented as API-fetched; requires owner confirmation",
        },
    ]
