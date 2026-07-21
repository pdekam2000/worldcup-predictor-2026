"""Multi-day owner discovery with explicit exclusions (odds classified separately)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.gpt_actions.competition_normalize import normalize_competition_key
from worldcup_predictor.gpt_actions.delegation import discover_today_matches
from worldcup_predictor.gpt_actions.owner_scope import fixture_tier
from worldcup_predictor.gpt_actions.tier_b_shadow_registry import TIER_B_SHADOW_DOMAINS
from worldcup_predictor.owner_daily.fixture_discovery import resolve_target_date
from worldcup_predictor.research.ecse_timing_experiment.constants import FRIENDLY_KEYS, PREMATCH, STARTED
from worldcup_predictor.research.ecse_timing_experiment.windows import to_vienna
from worldcup_predictor.research.forward_aligned_scan.constants import (
    DEFAULT_DAYS,
    MAX_DAYS,
    MIN_DAYS,
    TZ_NAME,
)

TZ = ZoneInfo(TZ_NAME)


def parse_days(days: int) -> int:
    d = int(days)
    if d < MIN_DAYS or d > MAX_DAYS:
        raise ValueError(f"--days must be between {MIN_DAYS} and {MAX_DAYS}, got {d}")
    return d


def vienna_date_range(*, from_date: str | None, days: int = DEFAULT_DAYS) -> dict[str, Any]:
    """Inclusive Vienna calendar range: from_date .. from_date+(days-1)."""
    days = parse_days(days)
    start = resolve_target_date(from_date or "today", TZ_NAME)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    end = start + timedelta(days=days - 1)
    # Midnight boundaries in Vienna
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=TZ)
    end_excl = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=TZ)
    return {
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "days": days,
        "dates": dates,
        "range_start_vienna": start_dt.isoformat(),
        "range_end_exclusive_vienna": end_excl.isoformat(),
        "timezone": TZ_NAME,
    }


def _league_country(competition: str | None) -> tuple[str, str]:
    canon = normalize_competition_key(competition) or str(competition or "unknown")
    try:
        comp = get_competition(canon)
        return comp.name, comp.country or "International"
    except Exception:
        meta = TIER_B_SHADOW_DOMAINS.get(canon) or {}
        return meta.get("name") or canon.replace("_", " ").title(), str(meta.get("country") or "UNKNOWN")


def _classify_status(status: str, listing: str | None, support: str | None, tier: Any, comp: str) -> str | None:
    st = str(status or "NS").upper()
    if comp in FRIENDLY_KEYS or str(listing or "").upper() == "FRIENDLY":
        return "BLOCKED_UNSUPPORTED:friendly"
    if str(support or "").upper() in {"FRIENDLY", "NO_PREDICTION_SUPPORT", "UNSUPPORTED"}:
        return f"BLOCKED_UNSUPPORTED:{support}"
    if str(tier).upper() not in {"A", "B"}:
        return "BLOCKED_UNSUPPORTED:non_owner_tier"
    if st in STARTED:
        return "BLOCKED_FIXTURE_STARTED"
    if st in {"CANC", "ABD", "PST", "SUSP", "INT", "AWD", "WO"}:
        return f"BLOCKED_STATUS:{st}"
    if st not in PREMATCH:
        return f"BLOCKED_STATUS:{st}"
    return None


def discover_range(
    *,
    from_date: str | None,
    days: int = DEFAULT_DAYS,
    scope: str = "owner",
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Discover all owner Tier A/B fixtures across the Vienna date range.

    Odds readiness is NOT decided here — every status/support exclusion is recorded.
    """
    rng = vienna_date_range(from_date=from_date, days=days)
    now = as_of or datetime.now(timezone.utc)
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    raw_total = 0
    by_date: dict[str, dict[str, Any]] = {}

    for day in rng["dates"]:
        raw = discover_today_matches(target_date=day, timezone=TZ_NAME, scope=scope)
        matches = list(raw.get("matches") or [])
        raw_total += len(matches)
        day_inc: list[dict[str, Any]] = []
        day_exc: list[dict[str, Any]] = []
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
                "kickoff_vienna": to_vienna(kickoff, TZ_NAME),
                "vienna_date": day,
                "tier": tier,
                "prediction_scope": pred_scope,
                "status": status,
                "source": m.get("source") or m.get("provider") or "owner_discovery",
            }
            if not fid:
                row = {**base, "discovery_status": "EXCLUDED", "exclusion_reason": "BLOCKED_UNSUPPORTED:missing_id"}
                excluded.append(row)
                day_exc.append(row)
                continue
            reason = _classify_status(
                status,
                m.get("listing_status"),
                m.get("prediction_support_status"),
                tier,
                comp,
            )
            if reason:
                row = {**base, "discovery_status": "EXCLUDED", "exclusion_reason": reason}
                excluded.append(row)
                day_exc.append(row)
                continue
            # Kickoff must fall on this Vienna calendar day
            try:
                ko = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                if ko.tzinfo is None:
                    ko = ko.replace(tzinfo=timezone.utc)
                if ko.astimezone(TZ).date().isoformat() != day:
                    row = {
                        **base,
                        "discovery_status": "EXCLUDED",
                        "exclusion_reason": "BLOCKED_STATUS:kickoff_outside_vienna_day",
                    }
                    excluded.append(row)
                    day_exc.append(row)
                    continue
            except Exception:
                pass
            row = {**base, "discovery_status": "INCLUDED", "exclusion_reason": None}
            included.append(row)
            day_inc.append(row)

        by_date[day] = {
            "raw": len(matches),
            "included": len(day_inc),
            "excluded": len(day_exc),
            "audit": raw.get("audit"),
        }

    # Dedupe by fixture_id (keep earliest kickoff row)
    by_fid: dict[int, dict[str, Any]] = {}
    for row in included:
        fid = int(row["fixture_id"])
        prev = by_fid.get(fid)
        if not prev or str(row.get("kickoff_utc") or "") < str(prev.get("kickoff_utc") or ""):
            by_fid[fid] = row
    included_unique = sorted(by_fid.values(), key=lambda r: (str(r.get("kickoff_utc") or ""), int(r["fixture_id"])))

    return {
        "range": rng,
        "as_of_utc": now.isoformat(),
        "scope": scope,
        "raw_discovered": raw_total,
        "included": included_unique,
        "excluded": excluded,
        "included_count": len(included_unique),
        "excluded_count": len(excluded),
        "by_date": by_date,
        "tier_a_count": sum(1 for x in included_unique if str(x.get("tier")).upper() == "A"),
        "tier_b_count": sum(1 for x in included_unique if str(x.get("tier")).upper() == "B"),
    }
