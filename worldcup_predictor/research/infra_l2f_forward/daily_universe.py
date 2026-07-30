"""Phase 6 — daily true-forward fixture universe (discovery + eligibility).

Records the full discovered set before selection. Excludes only with an
explicit reason. Never excludes for challenger disagreement, expected
performance, no_bet, or betting attractiveness.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from worldcup_predictor.gpt_actions.competition_normalize import normalize_competition_key
from worldcup_predictor.gpt_actions.delegation import discover_today_matches
from worldcup_predictor.gpt_actions.owner_scope import fixture_tier
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot

SCHEMA_VERSION = "l2f-hv-tf-universe-v1"
DEFAULT_TZ = "Europe/Vienna"

EXCL_UNSUPPORTED = "unsupported_competition"
EXCL_FRIENDLY = "friendly_excluded_by_canonical_policy"
EXCL_INVALID_IDENTITY = "invalid_fixture_identity"
EXCL_ALREADY_STARTED = "already_started"
EXCL_MISSING_INPUTS = "missing_mandatory_inputs"
EXCL_STALE_ODDS = "invalid_or_stale_odds_required"
EXCL_DUPLICATE = "duplicate_fixture"
EXCL_QUALITY_GATE = "canonical_quality_gate_rejection"
EXCL_CANCELLED = "cancelled_or_postponed"

CLASS_ELIGIBLE = "eligible"
CLASS_EXCLUDED = "excluded"

FRIENDLY_MARKERS = frozenset(
    {"friendlies", "friendly", "club_friendlies", "international_friendlies", "league_667"}
)
STARTED = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "PEN", "FT", "AET"})
CANCELLED = frozenset({"CANC", "ABD", "PST", "SUSP", "INT", "AWD", "WO"})
PREMATCH = frozenset({"NS", "TBD", "SCHEDULED", "TIMED", ""})
FRESH_OK = frozenset({"FRESH_ODDS", "ODDS_FRESH", "fresh", "Fresh"})


@dataclass
class UniverseFixture:
    fixture_id: int
    home_team: str | None
    away_team: str | None
    competition_key: str | None
    country: str | None
    kickoff_utc: str | None
    status: str | None
    validation_tier: str | None
    prediction_scope: str | None
    classification: str
    exclusion_reason: str | None = None
    odds_home: float | None = None
    odds_draw: float | None = None
    odds_away: float | None = None
    odds_freshness: str | None = None
    odds_bookmakers: int | None = None
    odds_strength_bucket: str = "unknown"
    market_balance_bucket: str = "unknown"
    expected_total_bucket: str = "unknown"
    has_immutable_freeze: bool = False
    already_tf_success: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip().replace(" ", "T")
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _f(v: Any) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def odds_strength_bucket(home: float | None, draw: float | None, away: float | None) -> str:
    """Prematch-observable favorite strength from decimal 1X2."""
    vals = [x for x in (home, draw, away) if x is not None and x > 1.0]
    if not vals:
        return "unknown"
    fav = min(vals)
    if fav <= 1.40:
        return "heavy_favorite"
    if fav <= 1.80:
        return "moderate_favorite"
    if fav <= 2.40:
        return "slight_favorite"
    return "open"


def market_balance_bucket(home: float | None, draw: float | None, away: float | None) -> str:
    if home is None or away is None or home <= 1 or away <= 1:
        return "unknown"
    ratio = max(home, away) / min(home, away)
    if ratio >= 3.0:
        return "one_sided"
    if ratio <= 1.35 and draw is not None and draw <= 3.60:
        return "balanced"
    return "mild_skew"


def expected_total_proxy_bucket(home: float | None, draw: float | None, away: float | None) -> str:
    """Rough prematch total proxy from 1X2 shape (not a model lambda)."""
    if home is None or draw is None or away is None:
        return "unknown"
    # Low draw price + short favorites → higher expected goals proxy
    fav = min(home, away)
    if draw <= 3.40 and fav <= 1.70:
        return "high_et_proxy"
    if draw >= 4.20 or fav >= 2.50:
        return "low_et_proxy"
    return "mid_et_proxy"


def _is_friendly(comp: str | None) -> bool:
    c = (comp or "").strip().lower()
    if not c:
        return False
    if c in FRIENDLY_MARKERS:
        return True
    return "friendly" in c


def classify_discovered_fixture(
    *,
    fixture_id: int | None,
    competition_key: str | None,
    status: str | None,
    kickoff_utc: str | None,
    validation_tier: str | None,
    now: datetime | None = None,
    seen_ids: set[int] | None = None,
    require_fresh_odds_for_eligibility: bool = False,
    odds_home: float | None = None,
    odds_draw: float | None = None,
    odds_away: float | None = None,
    odds_freshness: str | None = None,
) -> tuple[str, str | None]:
    """Return (classification, exclusion_reason)."""
    now = now or datetime.now(timezone.utc)
    if fixture_id is None or int(fixture_id) <= 0:
        return CLASS_EXCLUDED, EXCL_INVALID_IDENTITY
    fid = int(fixture_id)
    if seen_ids is not None and fid in seen_ids:
        return CLASS_EXCLUDED, EXCL_DUPLICATE

    comp = normalize_competition_key(competition_key) or str(competition_key or "")
    if _is_friendly(comp):
        return CLASS_EXCLUDED, EXCL_FRIENDLY

    tier = validation_tier or fixture_tier(comp)
    if tier not in ("A", "B"):
        return CLASS_EXCLUDED, EXCL_UNSUPPORTED

    st = str(status or "NS").upper()
    if st in CANCELLED:
        return CLASS_EXCLUDED, EXCL_CANCELLED
    if st in STARTED:
        return CLASS_EXCLUDED, EXCL_ALREADY_STARTED
    if st not in PREMATCH:
        return CLASS_EXCLUDED, EXCL_ALREADY_STARTED

    ko = _parse_dt(kickoff_utc)
    if ko is None:
        return CLASS_EXCLUDED, EXCL_MISSING_INPUTS
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=timezone.utc)
    if ko <= now:
        return CLASS_EXCLUDED, EXCL_ALREADY_STARTED

    if require_fresh_odds_for_eligibility:
        complete = bool(odds_home and odds_draw and odds_away and odds_home > 1 and odds_draw > 1 and odds_away > 1)
        fresh = str(odds_freshness or "") in FRESH_OK or str(odds_freshness or "").upper() in {
            "FRESH_ODDS",
            "ODDS_FRESH",
        }
        if not complete:
            return CLASS_EXCLUDED, EXCL_MISSING_INPUTS
        if not fresh:
            return CLASS_EXCLUDED, EXCL_STALE_ODDS

    return CLASS_ELIGIBLE, None


def _attach_odds(prod_conn: sqlite3.Connection | None, fixture_id: int) -> dict[str, Any]:
    if prod_conn is None:
        return {}
    try:
        snap = get_latest_valid_1x2_odds_snapshot(prod_conn, fixture_id)
    except Exception:
        return {}
    if snap is None:
        return {}
    home = _f(getattr(snap, "home_odds", None))
    draw = _f(getattr(snap, "draw_odds", None))
    away = _f(getattr(snap, "away_odds", None))
    freshness = getattr(snap, "freshness_class", None) or getattr(snap, "freshness_status", None)
    books = getattr(snap, "bookmaker_count", None)
    return {
        "odds_home": home,
        "odds_draw": draw,
        "odds_away": away,
        "odds_freshness": freshness,
        "odds_bookmakers": int(books) if books is not None else None,
    }


def _has_freeze(eval_conn: sqlite3.Connection | None, fixture_id: int) -> bool:
    if eval_conn is None:
        return False
    try:
        row = eval_conn.execute(
            """
            SELECT 1 FROM frozen_predictions
            WHERE fixture_id=? AND IFNULL(freeze_status,'ACTIVE')='ACTIVE'
            LIMIT 1
            """,
            (fixture_id,),
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def _tf_success(fi_conn: sqlite3.Connection | None, fixture_id: int) -> bool:
    if fi_conn is None:
        return False
    try:
        from worldcup_predictor.research.infra_l2f_forward.forward_hook import RUN_ID
        from worldcup_predictor.research.infra_l2f_forward.job_store import JOB_TABLE, ensure_job_schema

        ensure_job_schema(fi_conn)
        row = fi_conn.execute(
            f"SELECT 1 FROM {JOB_TABLE} WHERE fixture_id=? AND run_id=? AND status='success' LIMIT 1",
            (fixture_id, RUN_ID),
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def build_daily_universe(
    *,
    target_date: str,
    timezone_name: str = DEFAULT_TZ,
    scope: str = "owner",
    prod_conn: sqlite3.Connection | None = None,
    eval_conn: sqlite3.Connection | None = None,
    fi_conn: sqlite3.Connection | None = None,
    now: datetime | None = None,
    require_fresh_odds_for_eligibility: bool = False,
    discovery_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Discover + classify the full Vienna-day universe before sampling."""
    now = now or datetime.now(timezone.utc)
    discovery = discovery_payload or discover_today_matches(
        target_date=target_date, timezone=timezone_name, scope=scope
    )
    matches: list[dict[str, Any]] = list(discovery.get("matches") or [])
    seen: set[int] = set()
    rows: list[UniverseFixture] = []

    for m in matches:
        raw_id = m.get("fixture_id") or m.get("provider_fixture_id")
        try:
            fid = int(raw_id) if raw_id is not None else None
        except (TypeError, ValueError):
            fid = None
        comp = normalize_competition_key(m.get("competition_key") or m.get("competition")) or str(
            m.get("competition_key") or m.get("competition") or ""
        )
        tier = m.get("validation_tier") or m.get("tier") or fixture_tier(comp)
        status = str(m.get("status") or m.get("fixture_status") or "NS").upper()
        ko = m.get("kickoff_utc") or m.get("kickoff")
        odds = _attach_odds(prod_conn, fid) if fid else {}
        cls, reason = classify_discovered_fixture(
            fixture_id=fid,
            competition_key=comp,
            status=status,
            kickoff_utc=ko,
            validation_tier=str(tier) if tier else None,
            now=now,
            seen_ids=seen,
            require_fresh_odds_for_eligibility=require_fresh_odds_for_eligibility,
            odds_home=odds.get("odds_home"),
            odds_draw=odds.get("odds_draw"),
            odds_away=odds.get("odds_away"),
            odds_freshness=odds.get("odds_freshness"),
        )
        if fid is not None and cls == CLASS_ELIGIBLE:
            seen.add(fid)
        elif fid is not None and reason == EXCL_DUPLICATE:
            pass
        elif fid is not None:
            seen.add(fid)  # still mark identity for duplicate detection of later rows

        oh, od, oa = odds.get("odds_home"), odds.get("odds_draw"), odds.get("odds_away")
        row = UniverseFixture(
            fixture_id=int(fid or 0),
            home_team=m.get("home_team"),
            away_team=m.get("away_team"),
            competition_key=comp or None,
            country=m.get("country") or m.get("league_country"),
            kickoff_utc=str(ko) if ko else None,
            status=status,
            validation_tier=str(tier) if tier else None,
            prediction_scope="production" if tier == "A" else "owner_shadow",
            classification=cls,
            exclusion_reason=reason,
            odds_home=oh,
            odds_draw=od,
            odds_away=oa,
            odds_freshness=odds.get("odds_freshness"),
            odds_bookmakers=odds.get("odds_bookmakers"),
            odds_strength_bucket=odds_strength_bucket(oh, od, oa),
            market_balance_bucket=market_balance_bucket(oh, od, oa),
            expected_total_bucket=expected_total_proxy_bucket(oh, od, oa),
            has_immutable_freeze=_has_freeze(eval_conn, int(fid)) if fid else False,
            already_tf_success=_tf_success(fi_conn, int(fid)) if fid else False,
            metadata={
                "listing_status": m.get("listing_status"),
                "source": m.get("source"),
            },
        )
        rows.append(row)

    eligible = [r for r in rows if r.classification == CLASS_ELIGIBLE]
    excluded = [r for r in rows if r.classification != CLASS_ELIGIBLE]
    by_excl = Counter(r.exclusion_reason or "unknown" for r in excluded)
    by_league = Counter(r.competition_key or "unknown" for r in eligible)

    return {
        "schema_version": SCHEMA_VERSION,
        "target_date": target_date,
        "timezone": timezone_name,
        "scope": scope,
        "built_at_utc": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "discovered_count": len(rows),
        "eligible_count": len(eligible),
        "excluded_count": len(excluded),
        "exclusion_counts": dict(by_excl),
        "eligible_by_league": dict(by_league.most_common()),
        "discovery_meta": {
            k: discovery.get(k)
            for k in ("date", "timezone", "scope", "count", "tier_a_count", "tier_b_count")
            if k in discovery
        },
        "fixtures": [r.to_dict() for r in rows],
        "eligible_fixture_ids": [r.fixture_id for r in eligible],
        "policy_notes": {
            "no_bet_never_excludes": True,
            "challenger_disagreement_never_excludes": True,
            "require_fresh_odds_for_eligibility": require_fresh_odds_for_eligibility,
            "odds_gate_enforced_at_execution": True,
        },
    }


def eligible_rows(universe: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in (universe.get("fixtures") or []) if f.get("classification") == CLASS_ELIGIBLE]


def summarize_exclusions(universe: dict[str, Any]) -> dict[str, int]:
    return dict(universe.get("exclusion_counts") or {})
