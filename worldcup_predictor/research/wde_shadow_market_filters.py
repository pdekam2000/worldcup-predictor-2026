"""PHASE WDE-SHADOW-3 — Market-specific shadow signal filters (O/U2.5 + BTTS only)."""

from __future__ import annotations

from typing import Any

PHASE = "WDE-SHADOW-3"

OU25_STRONG_CONF = 0.60
OU25_MEDIUM_CONF = 0.55
OU25_HIGH_CONF_OVERRIDE = 0.65
BTTS_STRONG_CONF = 0.58
BTTS_MEDIUM_CONF = 0.53
SEVERE_MARKET_CONTRADICTION_SPREAD = 0.12


def _has_critical_missing(missing: list[str] | None) -> bool:
    if not missing:
        return False
    critical = {"odds_snapshot_missing", "critical_odds_implied_probs"}
    return bool(critical.intersection(set(missing)))


def _ou25_market_agrees(row: dict[str, Any]) -> bool:
    ou = row.get("ou25") or {}
    shadow = ou.get("shadow_pick")
    book = ou.get("bookmaker_pick")
    wde = ou.get("production_wde_pick")
    if shadow and book and shadow == book:
        return True
    if shadow and wde and shadow == wde:
        return True
    return False


def _btts_severe_contradiction(row: dict[str, Any]) -> bool:
    btts = row.get("btts") or {}
    shadow = btts.get("shadow_pick")
    conf = float(btts.get("shadow_confidence") or 0)
    book = btts.get("bookmaker_pick")
    if shadow and book and shadow != book and conf < 0.55:
        return True
    implied_yes = row.get("implied_prob_btts_yes")
    implied_no = row.get("implied_prob_btts_no")
    if implied_yes is not None and implied_no is not None:
        spread = abs(float(implied_yes) - float(implied_no))
        if shadow == "yes" and float(implied_yes) < 0.45 and spread >= SEVERE_MARKET_CONTRADICTION_SPREAD:
            return True
        if shadow == "no" and float(implied_no) < 0.45 and spread >= SEVERE_MARKET_CONTRADICTION_SPREAD:
            return True
    return False


def filter_ou25_signal(row: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    cautions: list[str] = []
    ou = row.get("ou25") or {}
    conf = float(ou.get("shadow_confidence") or 0)
    missing = row.get("missing_features") or []

    if _has_critical_missing(missing):
        return {
            "market": "ou25",
            "signal_badge": "DO_NOT_USE",
            "reasons": ["missing_critical_features"],
            "cautions": list(missing),
            "eligible_owner_report": False,
        }

    agrees = _ou25_market_agrees(row)
    if conf >= OU25_HIGH_CONF_OVERRIDE:
        reasons.append(f"high_shadow_confidence_{conf:.2f}")
    elif agrees:
        reasons.append("shadow_agrees_with_market_signal")
    elif conf < OU25_MEDIUM_CONF:
        cautions.append("low_shadow_confidence")

    if conf >= OU25_STRONG_CONF and (agrees or conf >= OU25_HIGH_CONF_OVERRIDE):
        badge = "STRONG_SHADOW_OU25"
        eligible = True
    elif conf >= OU25_MEDIUM_CONF and (agrees or conf >= OU25_STRONG_CONF):
        badge = "MEDIUM_SHADOW_OU25"
        eligible = True
    elif conf >= 0.50:
        badge = "WATCH_ONLY"
        eligible = False
        cautions.append("below_promotion_confidence_threshold")
    else:
        badge = "DO_NOT_USE"
        eligible = False
        reasons.append("insufficient_shadow_confidence")

    if row.get("disagreement_flags") and "ou25_vs_bookmaker" in row["disagreement_flags"]:
        cautions.append("disagrees_with_bookmaker")
        if badge == "STRONG_SHADOW_OU25" and conf < OU25_HIGH_CONF_OVERRIDE:
            badge = "MEDIUM_SHADOW_OU25"

    return {
        "market": "ou25",
        "signal_badge": badge,
        "reasons": reasons,
        "cautions": cautions,
        "eligible_owner_report": eligible,
    }


def filter_btts_signal(row: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    cautions: list[str] = []
    btts = row.get("btts") or {}
    conf = float(btts.get("shadow_confidence") or 0)
    missing = row.get("missing_features") or []

    if _has_critical_missing(missing):
        return {
            "market": "btts",
            "signal_badge": "DO_NOT_USE",
            "reasons": ["missing_critical_features"],
            "cautions": list(missing),
            "eligible_owner_report": False,
        }

    if _btts_severe_contradiction(row):
        return {
            "market": "btts",
            "signal_badge": "DO_NOT_USE",
            "reasons": ["severe_market_contradiction"],
            "cautions": ["shadow_pick_opposes_strong_market_implied"],
            "eligible_owner_report": False,
        }

    if conf >= BTTS_STRONG_CONF:
        reasons.append(f"shadow_confidence_{conf:.2f}")
        badge = "STRONG_SHADOW_BTTS"
        eligible = True
    elif conf >= BTTS_MEDIUM_CONF:
        badge = "MEDIUM_SHADOW_BTTS"
        eligible = True
        reasons.append(f"medium_confidence_{conf:.2f}")
    elif conf >= 0.50:
        badge = "WATCH_ONLY"
        eligible = False
        cautions.append("below_medium_threshold")
    else:
        badge = "DO_NOT_USE"
        eligible = False
        reasons.append("insufficient_shadow_confidence")

    if row.get("disagreement_flags") and "btts_vs_bookmaker" in row["disagreement_flags"]:
        cautions.append("disagrees_with_bookmaker")

    return {
        "market": "btts",
        "signal_badge": badge,
        "reasons": reasons,
        "cautions": cautions,
        "eligible_owner_report": eligible,
    }


def filter_1x2_signal(_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "market": "1x2",
        "signal_badge": "DO_NOT_USE",
        "reasons": ["1X2_PROMOTION_BLOCKED", "shadow underperformed bookmaker baseline on test"],
        "cautions": ["never_use_shadow_1x2_for_owner_picks"],
        "eligible_owner_report": False,
    }


def apply_market_filters(fixture_row: dict[str, Any]) -> dict[str, Any]:
    """Attach per-market filter output to a fixture prediction row."""
    filters = {
        "ou25": filter_ou25_signal(fixture_row),
        "btts": filter_btts_signal(fixture_row),
        "1x2": filter_1x2_signal(fixture_row),
    }
    eligible = (
        False
        if fixture_row.get("skipped")
        else filters["ou25"]["eligible_owner_report"] or filters["btts"]["eligible_owner_report"]
    )
    return {**fixture_row, "filters": filters, "eligible_owner_report": eligible}


def apply_filters_to_payload(payload: dict[str, Any]) -> dict[str, Any]:
    fixtures = [apply_market_filters(row) for row in payload.get("fixtures") or []]
    out = dict(payload)
    out["fixtures"] = fixtures
    out["filter_summary"] = summarize_filters(fixtures)
    return out


def summarize_filters(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    badges: dict[str, int] = {}
    for fx in fixtures:
        for market in ("ou25", "btts", "1x2"):
            badge = (fx.get("filters") or {}).get(market, {}).get("signal_badge")
            if badge:
                key = f"{market}:{badge}"
                badges[key] = badges.get(key, 0) + 1
    return {
        "total_fixtures": len(fixtures),
        "eligible_owner_report": sum(1 for f in fixtures if f.get("eligible_owner_report")),
        "badge_counts": badges,
        "1x2_always_blocked": True,
    }
