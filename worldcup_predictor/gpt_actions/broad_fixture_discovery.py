"""Broad fixture discovery for GPT Actions listing — provider + DB, not prediction-gated."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Literal

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import COMPETITION_REGISTRY, get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.forward_evaluation.fixture_model import enrich_unified_fixture, listing_status
from worldcup_predictor.gpt_actions.competition_normalize import (
    is_friendly_competition,
    normalize_competition_key,
)
from worldcup_predictor.gpt_actions.owner_scope import (
    DiscoveryScope,
    fixture_allowed_for_discovery,
    fixture_tier,
)
from worldcup_predictor.gpt_actions.tier_b_shadow_registry import TIER_B_SHADOW_DOMAINS
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture, vienna_day_utc_bounds

logger = logging.getLogger(__name__)

PREMATCH_STATUSES = frozenset({"NS", "TBD", "SCHEDULED", "NOT STARTED", "TIMED", ""})
EXCLUDED_STATUSES = frozenset({"CANC", "ABD", "PST", "SUSP", "INT", "AWD", "WO"})
LIVE_STATUSES = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "PEN"})
FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})

_LEAGUE_ID_TO_TIER_A: dict[int, str] = {
    comp.league_id: key for key, comp in COMPETITION_REGISTRY.items() if comp.enabled and comp.league_id
}
_LEAGUE_ID_TO_TIER_B: dict[int, str] = {
    int(meta["provider_league_id"]): key for key, meta in TIER_B_SHADOW_DOMAINS.items()
}


@dataclass
class BroadDiscoveryAudit:
    provider_raw_count: int = 0
    provider_fetch_attempted: bool = False
    provider_fetch_ok: bool = False
    provider_error: str | None = None
    db_window_count: int = 0
    deduplicated_count: int = 0
    prematch_count: int = 0
    tier_a_count: int = 0
    tier_b_count: int = 0
    friendly_count: int = 0
    unsupported_count: int = 0
    odds_missing_count: int = 0
    prediction_candidate_count: int = 0
    synced_to_db_count: int = 0
    source_order: list[str] = field(default_factory=lambda: ["api_football_cache", "local_db"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_raw_count": self.provider_raw_count,
            "provider_fetch_attempted": self.provider_fetch_attempted,
            "provider_fetch_ok": self.provider_fetch_ok,
            "provider_error": self.provider_error,
            "db_window_count": self.db_window_count,
            "deduplicated_count": self.deduplicated_count,
            "prematch_count": self.prematch_count,
            "tier_a_count": self.tier_a_count,
            "tier_b_count": self.tier_b_count,
            "friendly_count": self.friendly_count,
            "unsupported_count": self.unsupported_count,
            "odds_missing_count": self.odds_missing_count,
            "prediction_candidate_count": self.prediction_candidate_count,
            "synced_to_db_count": self.synced_to_db_count,
            "source_order": list(self.source_order),
        }


def _is_prematch(status: str | None) -> bool:
    s = (status or "NS").upper().strip()
    if s in EXCLUDED_STATUSES or s in FINISHED_STATUSES or s in LIVE_STATUSES:
        return False
    return s in PREMATCH_STATUSES or s == ""


def _kickoff_in_window(kickoff_utc: str, start_utc: str, end_utc: str) -> bool:
    if not kickoff_utc:
        return False
    try:
        raw = kickoff_utc.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        start = datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_utc.replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return start <= dt <= end
    except (ValueError, TypeError):
        return False


def resolve_competition_key_from_league(league_id: int, league: dict[str, Any] | None = None) -> str:
    league = league or {}
    league_type = str(league.get("type") or "").lower()
    if league_id == 667 or "friendly" in league_type:
        return "league_667"
    if league_id in _LEAGUE_ID_TO_TIER_A:
        return _LEAGUE_ID_TO_TIER_A[league_id]
    if league_id in _LEAGUE_ID_TO_TIER_B:
        return _LEAGUE_ID_TO_TIER_B[league_id]
    return f"league_{league_id}"


def _fetch_api_fixtures_for_date(settings: Settings, target: date) -> tuple[list[dict[str, Any]], str | None]:
    client = ApiFootballClient(settings)
    if not client.is_configured:
        return [], "api_football_not_configured"
    result = client._safe_get(
        "fixtures",
        {"date": target.isoformat()},
        placeholder_factory=lambda: None,
        ttl_seconds=300,
    )
    if not result or not result.data:
        return [], result.error if result else "empty_provider_response"
    items = [item for item in result.data if isinstance(item, dict)]
    return items, None


def _parse_api_item(item: dict[str, Any]) -> dict[str, Any] | None:
    league = item.get("league") or {}
    league_id = int(league.get("id") or 0)
    if not league_id:
        return None
    fx = item.get("fixture") or {}
    teams = item.get("teams") or {}
    status = str((fx.get("status") or {}).get("short") or "NS").upper()
    fid = int(fx.get("id") or 0)
    if not fid:
        return None
    comp_key = resolve_competition_key_from_league(league_id, league)
    return {
        "fixture_id": fid,
        "home_team": str((teams.get("home") or {}).get("name") or "TBD"),
        "away_team": str((teams.get("away") or {}).get("name") or "TBD"),
        "competition_key": comp_key,
        "competition_raw": comp_key,
        "kickoff_utc": str(fx.get("date") or ""),
        "status": status,
        "season": int(league.get("season") or 0) or None,
        "league_id": league_id,
        "coverage_sources": ["api_football"],
        "api_item": item,
    }


def _load_db_fixtures_in_window(conn, *, start_utc: str, end_utc: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status, season
        FROM fixtures
        WHERE is_placeholder = 0
          AND kickoff_utc IS NOT NULL
          AND kickoff_utc >= ?
          AND kickoff_utc <= ?
        ORDER BY kickoff_utc ASC
        LIMIT 2000
        """,
        (start_utc, end_utc),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        out.append(
            {
                "fixture_id": int(row["fixture_id"]),
                "home_team": str(row.get("home_team") or "TBD"),
                "away_team": str(row.get("away_team") or "TBD"),
                "competition_key": str(row.get("competition_key") or "unknown"),
                "competition_raw": str(row.get("competition_key") or "unknown"),
                "kickoff_utc": str(row.get("kickoff_utc") or ""),
                "status": str(row.get("status") or "NS"),
                "season": int(row["season"]) if row.get("season") is not None else None,
                "coverage_sources": ["local_db"],
                "api_item": None,
            }
        )
    return out


def _merge_fixture_records(
    api_rows: list[dict[str, Any]],
    db_rows: list[dict[str, Any]],
    *,
    start_utc: str,
    end_utc: str,
) -> list[dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    for row in api_rows:
        if not _is_prematch(row.get("status")):
            continue
        if not _kickoff_in_window(str(row.get("kickoff_utc") or ""), start_utc, end_utc):
            continue
        fid = int(row["fixture_id"])
        by_id[fid] = dict(row)
    for row in db_rows:
        if not _is_prematch(row.get("status")):
            continue
        fid = int(row["fixture_id"])
        if fid in by_id:
            existing = by_id[fid]
            sources = list(existing.get("coverage_sources") or [])
            if "local_db" not in sources:
                sources.append("local_db")
            existing["coverage_sources"] = sources
            if existing.get("competition_key", "").startswith("league_") and not str(
                row.get("competition_key", "")
            ).startswith("league_"):
                existing["competition_key"] = row["competition_key"]
                existing["competition_raw"] = row.get("competition_raw") or row["competition_key"]
            continue
        by_id[fid] = dict(row)
    return sorted(by_id.values(), key=lambda r: str(r.get("kickoff_utc") or ""))


def _prediction_support_status(comp_key: str, *, odds_available: bool | None) -> str:
    if is_friendly_competition(comp_key):
        return "FRIENDLY"
    tier = fixture_tier(comp_key)
    if tier == "A":
        return "TRUSTED"
    if tier == "B":
        return "TEST_PHASE"
    if odds_available is False:
        return "ODDS_MISSING"
    return "NO_PREDICTION_SUPPORT"


def classify_broad_record(
    record: dict[str, Any],
    *,
    odds_available: bool | None = None,
) -> dict[str, Any]:
    comp = str(record.get("competition_key") or "unknown")
    canon = normalize_competition_key(comp) or comp
    tier = fixture_tier(comp)
    ls = listing_status(comp, odds_available=odds_available)
    support = _prediction_support_status(comp, odds_available=odds_available)
    unified = enrich_unified_fixture(
        fixture_id=int(record["fixture_id"]),
        home_team=str(record.get("home_team") or "TBD"),
        away_team=str(record.get("away_team") or "TBD"),
        competition_key=comp,
        kickoff_utc=str(record.get("kickoff_utc") or ""),
        status=str(record.get("status") or "NS"),
        scope="owner",
        listing_only=True,
        odds_available=odds_available,
    )
    unified.update(
        {
            "competition": canon,
            "competition_raw": record.get("competition_raw") or comp,
            "listing_status": ls,
            "prediction_support_status": support,
            "exclusion_reason": None if tier in ("A", "B") else support,
            "coverage_sources": record.get("coverage_sources") or [],
            "discovery_source": ",".join(record.get("coverage_sources") or []),
        }
    )
    return unified


def _sync_prediction_candidates_to_db(
    records: list[dict[str, Any]],
    *,
    settings: Settings,
) -> int:
    """Upsert Tier A+B fixtures from broad discovery so prediction jobs can resolve DB rows."""
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    synced = 0
    for rec in records:
        comp_key = normalize_competition_key(str(rec.get("competition_key") or "")) or str(
            rec.get("competition_key") or ""
        )
        tier = fixture_tier(comp_key)
        if tier not in ("A", "B"):
            continue
        api_item = rec.get("api_item")
        if not api_item:
            continue
        parsed = parse_api_fixture_item(api_item, source="api_football")
        if not parsed:
            continue
        if tier == "A":
            try:
                comp = get_competition(comp_key)
                repo.upsert_competition(comp)
            except KeyError:
                continue
        elif tier == "B":
            from worldcup_predictor.gpt_actions.wde_runtime import register_tier_b_competition_runtime

            if register_tier_b_competition_runtime(comp_key, repo=repo, season=rec.get("season")) is None:
                continue
        repo.upsert_fixture(
            parsed,
            competition_key=comp_key,
            league_id=int(rec.get("league_id") or 0) or None,
            season=rec.get("season"),
        )
        synced += 1
    if synced:
        repo._conn.commit()
    return synced


def discover_broad_fixtures(
    *,
    target_date: str,
    timezone: str = "Europe/Vienna",
    settings: Settings | None = None,
    sync_prediction_candidates: bool = False,
) -> dict[str, Any]:
    """
    Broad listing discovery — all prematch fixtures in Vienna window from API cache + DB.

    Not prediction-gated. Classification only.
    """
    settings = settings or get_settings()
    d = date.fromisoformat(target_date)
    start_utc, end_utc = vienna_day_utc_bounds(d, timezone)
    audit = BroadDiscoveryAudit()

    api_items, api_err = _fetch_api_fixtures_for_date(settings, d)
    audit.provider_fetch_attempted = True
    audit.provider_raw_count = len(api_items)
    audit.provider_fetch_ok = api_err is None and len(api_items) > 0
    audit.provider_error = api_err

    api_rows = [_parse_api_item(item) for item in api_items]
    api_rows = [r for r in api_rows if r is not None]

    conn = connect(settings.sqlite_path)
    try:
        db_rows = _load_db_fixtures_in_window(conn, start_utc=start_utc, end_utc=end_utc)
        audit.db_window_count = len(db_rows)
        merged = _merge_fixture_records(api_rows, db_rows, start_utc=start_utc, end_utc=end_utc)
        audit.deduplicated_count = len(merged)
        audit.prematch_count = len(merged)

        from worldcup_predictor.gpt_actions.delegation import _match_odds

        classified: list[dict[str, Any]] = []
        for rec in merged:
            fid = int(rec["fixture_id"])
            odds = _match_odds(conn, fid)
            odds_available = int(odds.get("bookmaker_count") or 0) > 0
            row = classify_broad_record(rec, odds_available=odds_available)
            classified.append(row)
            ls = row.get("listing_status")
            tier = row.get("validation_tier")
            if tier == "A":
                audit.tier_a_count += 1
            elif tier == "B":
                audit.tier_b_count += 1
            elif ls == "FRIENDLY" or row.get("prediction_support_status") == "FRIENDLY":
                audit.friendly_count += 1
            elif ls == "UNSUPPORTED" or row.get("prediction_support_status") == "NO_PREDICTION_SUPPORT":
                audit.unsupported_count += 1
            if row.get("prediction_support_status") == "ODDS_MISSING":
                audit.odds_missing_count += 1
            if tier in ("A", "B"):
                audit.prediction_candidate_count += 1

        if sync_prediction_candidates:
            audit.synced_to_db_count = _sync_prediction_candidates_to_db(merged, settings=settings)

        return {
            "date": target_date,
            "timezone": timezone,
            "mode": "broad_listing",
            "audit": audit.to_dict(),
            "count": len(classified),
            "tier_a_count": audit.tier_a_count,
            "tier_b_count": audit.tier_b_count,
            "friendly_count": audit.friendly_count,
            "unsupported_count": audit.unsupported_count,
            "odds_missing_count": audit.odds_missing_count,
            "prediction_candidate_count": audit.prediction_candidate_count,
            "matches": classified,
        }
    finally:
        conn.close()


def discover_prediction_candidates_from_broad(
    *,
    target_date: str,
    timezone: str = "Europe/Vienna",
    scope: DiscoveryScope = "owner",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Prediction candidate discovery from broad source — Tier filter applied after classification."""
    settings = settings or get_settings()
    broad = discover_broad_fixtures(
        target_date=target_date,
        timezone=timezone,
        settings=settings,
        sync_prediction_candidates=True,
    )
    matches: list[dict[str, Any]] = []
    for m in broad.get("matches") or []:
        daily = DailyFixture(
            fixture_id=int(m["fixture_id"]),
            provider_fixture_id=int(m["fixture_id"]),
            competition_key=str(m.get("competition_raw") or m.get("competition") or ""),
            home_team=str(m.get("home_team") or "TBD"),
            away_team=str(m.get("away_team") or "TBD"),
            kickoff_utc=str(m.get("kickoff_utc") or m.get("kickoff") or ""),
            status=str(m.get("status") or "NS"),
            season=None,
        )
        if fixture_allowed_for_discovery(daily, scope):
            matches.append(m)
    tier_a = sum(1 for m in matches if m.get("validation_tier") == "A")
    tier_b = sum(1 for m in matches if m.get("validation_tier") == "B")
    return {
        "date": target_date,
        "timezone": timezone,
        "scope": scope,
        "count": len(matches),
        "tier_a_count": tier_a,
        "tier_b_count": tier_b,
        "broad_audit": broad.get("audit"),
        "matches": matches,
    }
