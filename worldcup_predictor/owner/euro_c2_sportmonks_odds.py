"""PHASE EURO-C2 — Sportmonks UEFA odds crosswalk + import (owner/internal only)."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.data_import.european_fixture_feed import ensure_euro_fixture_feed_tables
from worldcup_predictor.data_import.uefa_result_matching import (
    KICKOFF_WINDOW_HOURS,
    FeedIndex,
    kickoff_delta_hours,
    load_raw_payload,
    parse_kickoff,
    team_similarity,
    teams_exact,
    teams_fuzzy_score,
)
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.uefa_club.config import UEFA_FULL_INCLUDES
from worldcup_predictor.egie.uefa_club.odds_intelligence import MARKET_ALIASES, _market_key
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache
from worldcup_predictor.owner.euro_c_odds_import import (
    GENERATED_BY_WDE,
    _existing_is_newer_than,
    _latest_odds_snapshot,
    _markets_complete,
    assess_ecse_readiness,
    filter_uefa_target_fixtures,
    is_fake_odds_payload,
    normalize_uefa_odds_snapshot,
)
from worldcup_predictor.owner_daily.odds_import import _sportmonks_lines_to_bookmakers
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.research.safe_bets.providers import fetch_sportmonks_odds_from_cache

PHASE = "EURO-C2"
MIN_CROSSWALK_CONFIDENCE = 0.90
AMBIGUOUS_TOP_DELTA = 0.02
MatchType = Literal["exact", "high_confidence", "ambiguous", "no_match"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _time_match_score(delta_hours: float | None, api_kickoff: str, sm_kickoff: str) -> float:
    if delta_hours is None:
        return 0.0
    if delta_hours <= KICKOFF_WINDOW_HOURS:
        return round(1.0 - delta_hours / KICKOFF_WINDOW_HOURS, 4)
    # Sportmonks euro feed often stores date-only midnight UTC while API-Football has true kickoff.
    api_dt = parse_kickoff(api_kickoff)
    sm_dt = parse_kickoff(sm_kickoff)
    if api_dt and sm_dt and api_dt.date() == sm_dt.date() and delta_hours <= 24:
        return 0.93
    return 0.0


def _classify_match_type(
    *,
    home_score: float,
    away_score: float,
    time_score: float,
    combined: float,
    exact_teams: bool,
) -> MatchType:
    if combined < MIN_CROSSWALK_CONFIDENCE:
        return "no_match"
    if exact_teams and time_score >= 0.95:
        return "exact"
    if combined >= MIN_CROSSWALK_CONFIDENCE:
        return "high_confidence"
    return "no_match"


def _load_sportmonks_feed_rows(
    conn: sqlite3.Connection,
    *,
    competition_keys: list[str],
    days_ahead: int,
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    end = now + timedelta(days=max(1, days_ahead))
    placeholders = ",".join("?" for _ in competition_keys)
    rows = conn.execute(
        f"""
        SELECT fixture_id, provider_fixture_id, competition_key, home_team, away_team,
               kickoff_utc, status, raw_payload_ref
        FROM euro_fixture_feed
        WHERE provider = 'sportmonks'
          AND competition_key IN ({placeholders})
          AND kickoff_utc >= ?
          AND kickoff_utc <= ?
        ORDER BY kickoff_utc ASC
        """,
        (*competition_keys, now.isoformat(), end.isoformat()),
    ).fetchall()
    return [dict(r) for r in rows]


@dataclass
class CrosswalkCandidate:
    api_football_fixture_id: int
    sportmonks_fixture_id: int
    competition_key: str
    api_home_team: str
    api_away_team: str
    api_kickoff_utc: str
    sportmonks_home_team: str
    sportmonks_away_team: str
    sportmonks_kickoff_utc: str
    time_match_score: float
    home_team_score: float
    away_team_score: float
    combined_confidence: float
    match_type: MatchType
    match_reason: str
    accepted: bool
    ambiguous: bool = False
    candidate_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_football_fixture_id": self.api_football_fixture_id,
            "sportmonks_fixture_id": self.sportmonks_fixture_id,
            "competition_key": self.competition_key,
            "teams": {
                "api_home": self.api_home_team,
                "api_away": self.api_away_team,
                "sportmonks_home": self.sportmonks_home_team,
                "sportmonks_away": self.sportmonks_away_team,
            },
            "kickoff_times": {
                "api_football": self.api_kickoff_utc,
                "sportmonks": self.sportmonks_kickoff_utc,
            },
            "time_match_score": self.time_match_score,
            "home_team_score": self.home_team_score,
            "away_team_score": self.away_team_score,
            "combined_confidence": self.combined_confidence,
            "match_type": self.match_type,
            "match_reason": self.match_reason,
            "accepted": self.accepted,
            "ambiguous": self.ambiguous,
            "candidate_count": self.candidate_count,
        }


def _score_crosswalk_candidate(
    api_home: str,
    api_away: str,
    api_kickoff: str,
    sm_row: dict[str, Any],
) -> tuple[float, float, float, float, bool] | None:
    dh = kickoff_delta_hours(api_kickoff, str(sm_row.get("kickoff_utc") or ""))
    time_score = _time_match_score(dh, api_kickoff, str(sm_row.get("kickoff_utc") or ""))
    if time_score <= 0:
        return None
    home_score = team_similarity(api_home, str(sm_row.get("home_team") or ""))
    away_score = team_similarity(api_away, str(sm_row.get("away_team") or ""))
    fuzzy = teams_fuzzy_score(
        api_home, api_away, str(sm_row.get("home_team") or ""), str(sm_row.get("away_team") or "")
    )
    combined = round((time_score + home_score + away_score) / 3.0, 4)
    if fuzzy >= 0.88:
        combined = max(combined, round((time_score + fuzzy) / 2.0, 4))
    exact = teams_exact(
        api_home, api_away, str(sm_row.get("home_team") or ""), str(sm_row.get("away_team") or "")
    )
    return time_score, home_score, away_score, combined, exact


def build_uefa_sportmonks_crosswalk(
    conn: sqlite3.Connection,
    *,
    competition_keys: list[str] | None = None,
    days_ahead: int = 30,
) -> dict[str, Any]:
    ensure_euro_fixture_feed_tables(conn)
    keys = list(competition_keys or UEFA_CUP_KEYS)
    feed_index = FeedIndex.build(conn, tuple(keys))
    api_fixtures = filter_uefa_target_fixtures(conn, competition_keys=keys, days_ahead=days_ahead)
    sm_rows = _load_sportmonks_feed_rows(conn, competition_keys=keys, days_ahead=days_ahead)

    matches: list[CrosswalkCandidate] = []
    rejected: list[dict[str, Any]] = []

    for sel in api_fixtures:
        api_id = sel.provider_fixture_id
        comp = sel.competition_key
        scored: list[tuple[float, dict[str, Any], tuple]] = []

        for sm in sm_rows:
            if str(sm.get("competition_key")) != comp:
                continue
            scored_tuple = _score_crosswalk_candidate(
                sel.home_team, sel.away_team, sel.kickoff_utc, sm
            )
            if scored_tuple is None:
                continue
            time_score, home_score, away_score, combined, exact = scored_tuple
            if combined < MIN_CROSSWALK_CONFIDENCE:
                continue
            scored.append((combined, sm, (time_score, home_score, away_score, exact)))

        scored.sort(key=lambda x: x[0], reverse=True)
        ambiguous = False
        if len(scored) >= 2 and (scored[0][0] - scored[1][0]) < AMBIGUOUS_TOP_DELTA:
            ambiguous = True

        if not scored:
            rejected.append(
                {
                    "api_football_fixture_id": api_id,
                    "competition_key": comp,
                    "home_team": sel.home_team,
                    "away_team": sel.away_team,
                    "reason": "no_sportmonks_candidate",
                }
            )
            matches.append(
                CrosswalkCandidate(
                    api_football_fixture_id=api_id,
                    sportmonks_fixture_id=0,
                    competition_key=comp,
                    api_home_team=sel.home_team,
                    api_away_team=sel.away_team,
                    api_kickoff_utc=sel.kickoff_utc,
                    sportmonks_home_team="",
                    sportmonks_away_team="",
                    sportmonks_kickoff_utc="",
                    time_match_score=0.0,
                    home_team_score=0.0,
                    away_team_score=0.0,
                    combined_confidence=0.0,
                    match_type="no_match",
                    match_reason="no_sportmonks_candidate",
                    accepted=False,
                    candidate_count=0,
                )
            )
            continue

        best_combined, best_sm, (time_score, home_score, away_score, exact) = scored[0]
        match_type = _classify_match_type(
            home_score=home_score,
            away_score=away_score,
            time_score=time_score,
            combined=best_combined,
            exact_teams=exact,
        )
        if ambiguous:
            match_type = "ambiguous"

        feed_key = (comp, "sportmonks", int(best_sm["provider_fixture_id"]))
        reason_parts = [f"combined={best_combined:.3f}"]
        if feed_key in feed_index.by_provider_id:
            reason_parts.append("euro_feed_index")
        if exact:
            reason_parts.append("teams_exact")
        else:
            reason_parts.append("teams_fuzzy")

        accepted = (
            not ambiguous
            and match_type in {"exact", "high_confidence"}
            and best_combined >= MIN_CROSSWALK_CONFIDENCE
        )

        candidate = CrosswalkCandidate(
            api_football_fixture_id=api_id,
            sportmonks_fixture_id=int(best_sm["provider_fixture_id"]),
            competition_key=comp,
            api_home_team=sel.home_team,
            api_away_team=sel.away_team,
            api_kickoff_utc=sel.kickoff_utc,
            sportmonks_home_team=str(best_sm.get("home_team") or ""),
            sportmonks_away_team=str(best_sm.get("away_team") or ""),
            sportmonks_kickoff_utc=str(best_sm.get("kickoff_utc") or ""),
            time_match_score=time_score,
            home_team_score=home_score,
            away_team_score=away_score,
            combined_confidence=best_combined,
            match_type=match_type,
            match_reason="|".join(reason_parts),
            accepted=accepted,
            ambiguous=ambiguous,
            candidate_count=len(scored),
        )
        matches.append(candidate)
        if not accepted:
            rejected.append(
                {
                    "api_football_fixture_id": api_id,
                    "sportmonks_fixture_id": candidate.sportmonks_fixture_id,
                    "match_type": match_type,
                    "combined_confidence": best_combined,
                    "reason": "ambiguous" if ambiguous else "below_threshold_or_no_match",
                }
            )

    accepted_rows = [m for m in matches if m.accepted]
    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now_iso(),
        "min_crosswalk_confidence": MIN_CROSSWALK_CONFIDENCE,
        "api_fixtures_targeted": len(api_fixtures),
        "sportmonks_feed_rows": len(sm_rows),
        "accepted_count": len(accepted_rows),
        "rejected_count": len(rejected),
        "ambiguous_count": sum(1 for m in matches if m.ambiguous),
        "no_match_count": sum(1 for m in matches if m.match_type == "no_match"),
        "matches": [m.to_dict() for m in matches],
        "rejected": rejected[:200],
        "accepted": [m.to_dict() for m in accepted_rows],
    }


def _float_odd(value: Any) -> float | None:
    try:
        if value is None:
            return None
        num = float(value)
        return num if num > 1.0 else None
    except (TypeError, ValueError):
        return None


def _sm_selection_label(market_key: str | None, entry: dict[str, Any]) -> str | None:
    label = str(entry.get("label") or entry.get("name") or "").strip()
    side = label.lower()
    if market_key == "match_winner":
        return {"1": "Home", "home": "Home", "x": "Draw", "draw": "Draw", "2": "Away", "away": "Away"}.get(side, label.title() if label else None)
    if market_key == "btts":
        return "Yes" if side in {"yes", "btts: yes"} else "No" if side in {"no", "btts: no"} else None
    if market_key == "over_under":
        total = str(entry.get("total") or entry.get("handicap") or "").strip()
        if not total:
            return None
        if side in {"yes", "over"}:
            return f"Over {total}"
        if side in {"no", "under"}:
            return f"Under {total}"
    if market_key == "correct_score":
        return label if label else None
    if market_key == "double_chance":
        return label if label else None
    return label or None


def _sm_market_display_name(market_key: str | None, entry: dict[str, Any]) -> str:
    if market_key == "match_winner":
        return "Match Winner"
    if market_key == "btts":
        return "Both Teams Score"
    if market_key == "over_under":
        return "Goals Over/Under"
    if market_key == "correct_score":
        return "Correct Score"
    if market_key == "double_chance":
        return "Double Chance"
    return str((entry.get("market") or {}).get("name") or entry.get("market_description") or "Market")


def sportmonks_odds_to_bookmakers(odds_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Sportmonks odds[] into API-Football-compatible bookmaker blocks."""
    by_book: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for entry in odds_entries:
        if not isinstance(entry, dict):
            continue
        mname = str((entry.get("market") or {}).get("name") or entry.get("market_description") or "")
        mkey = _market_key(mname)
        if mkey not in {
            "match_winner",
            "btts",
            "over_under",
            "correct_score",
            "double_chance",
        }:
            continue
        odd = _float_odd(entry.get("value") or entry.get("dp3") or entry.get("odd"))
        if odd is None:
            continue
        selection = _sm_selection_label(mkey, entry)
        if not selection:
            continue
        bm_name = str((entry.get("bookmaker") or {}).get("name") or "Sportmonks")
        market_name = _sm_market_display_name(mkey, entry)
        by_book[bm_name][market_name].append({"value": selection, "odd": str(odd)})

    out: list[dict[str, Any]] = []
    for bm_name, markets in by_book.items():
        bets = [{"name": mname, "values": vals} for mname, vals in markets.items() if vals]
        if bets:
            out.append({"name": bm_name, "bets": bets})
    return out


def _extract_fixture_data(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload.get("payload"), dict):
        inner = payload["payload"]
        if isinstance(inner.get("data"), dict):
            return inner["data"]
    return payload


def load_sportmonks_odds_payload(
    conn: sqlite3.Connection,
    sportmonks_fixture_id: int,
    *,
    settings: Settings | None = None,
    sm_row: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str, str | None]:
    """Return (fixture_data, source, raw_path)."""
    settings = settings or get_settings()
    sm_id = int(sportmonks_fixture_id)

    cache_file = cache_path(settings, sm_id)
    cached = load_cache(cache_file)
    if cached:
        data = _extract_fixture_data(cached.get("payload") or cached)
        if data.get("odds"):
            return data, "uefa_club_raw_cache", str(cache_file)

    if sm_row:
        raw = load_raw_payload(conn, str(sm_row.get("raw_payload_ref") or ""))
        if raw:
            data = _extract_fixture_data(raw)
            if data.get("odds"):
                return data, "euro_fixture_raw_payload", str(sm_row.get("raw_payload_ref"))

    enrich = None
    try:
        row = conn.execute(
            """
            SELECT raw_json FROM sportmonks_fixture_enrichment
            WHERE sportmonks_fixture_id = ? AND status = 'ok'
            ORDER BY id DESC LIMIT 1
            """,
            (sm_id,),
        ).fetchone()
        if row:
            enrich = json.loads(row["raw_json"])
    except (sqlite3.OperationalError, json.JSONDecodeError, TypeError):
        enrich = None
    if enrich:
        data = _extract_fixture_data(enrich)
        if data.get("odds"):
            return data, "sportmonks_fixture_enrichment", None

    api_cached = fetch_sportmonks_odds_from_cache(conn, sm_id)
    if api_cached.lines:
        bookmakers = _sportmonks_lines_to_bookmakers(api_cached.lines)
        if bookmakers:
            return {"odds": [], "_bookmakers": bookmakers}, "sportmonks_enrichment_cache", None

    return None, "none", None


def fetch_sportmonks_odds_live(
    sportmonks_fixture_id: int,
    *,
    settings: Settings | None = None,
    force_refresh: bool = False,
) -> tuple[dict[str, Any] | None, str, str | None]:
    settings = settings or get_settings()
    sm_id = int(sportmonks_fixture_id)
    if not force_refresh:
        cached = load_cache(cache_path(settings, sm_id))
        if cached:
            data = _extract_fixture_data(cached.get("payload") or cached)
            if data.get("odds"):
                return data, "uefa_club_raw_cache", str(cache_path(settings, sm_id))

    provider = SportmonksProvider(settings)
    if not provider.is_configured:
        return None, "sportmonks_not_configured", None

    status, payload, error = provider.safe_get(
        f"/fixtures/{sm_id}",
        params={"include": UEFA_FULL_INCLUDES},
    )
    if error or not isinstance(payload, dict):
        return None, f"live_error:{error}", None
    data = _extract_fixture_data(payload)
    if not data.get("odds"):
        return None, "live_empty_odds", None

    cache_file = cache_path(settings, sm_id)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "sportmonks_fixture_id": sm_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "status_code": status,
        "payload": payload,
        "phase": PHASE,
    }
    cache_file.write_text(json.dumps(envelope, indent=2, default=str), encoding="utf-8")
    return data, "sportmonks_live", str(cache_file)


def fixture_data_to_bookmakers(fixture_data: dict[str, Any]) -> list[dict[str, Any]]:
    if fixture_data.get("_bookmakers"):
        return list(fixture_data["_bookmakers"])
    odds = fixture_data.get("odds") or []
    if not isinstance(odds, list):
        return []
    return sportmonks_odds_to_bookmakers(odds)


def scan_crosswalk_odds_availability(
    conn: sqlite3.Connection,
    crosswalk: dict[str, Any],
    *,
    settings: Settings | None = None,
    max_api_calls: int = 0,
    cache_first: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    settings = settings or get_settings()
    accepted = [m for m in crosswalk.get("accepted") or [] if m.get("accepted")]
    sm_feed = _load_sportmonks_feed_rows(
        conn,
        competition_keys=list({m["competition_key"] for m in accepted} or UEFA_CUP_KEYS),
        days_ahead=30,
    )
    sm_by_id = {int(r["provider_fixture_id"]): r for r in sm_feed}

    api_calls = 0
    rows: list[dict[str, Any]] = []
    for item in accepted:
        api_id = int(item["api_football_fixture_id"])
        sm_id = int(item["sportmonks_fixture_id"])
        sm_row = sm_by_id.get(sm_id)

        fixture_data, source, raw_path = (None, "none", None)
        if cache_first:
            fixture_data, source, raw_path = load_sportmonks_odds_payload(
                conn, sm_id, settings=settings, sm_row=sm_row
            )

        if not fixture_data and max_api_calls > 0 and api_calls < max_api_calls and not dry_run:
            fixture_data, source, raw_path = fetch_sportmonks_odds_live(sm_id, settings=settings)
            if source == "sportmonks_live":
                api_calls += 1
        elif not fixture_data and dry_run and max_api_calls > api_calls:
            source = "would_fetch_live"
            api_calls += 1

        bookmakers: list[dict[str, Any]] = []
        if fixture_data:
            bookmakers = fixture_data_to_bookmakers(fixture_data)

        normalized = normalize_uefa_odds_snapshot(bookmakers, fixture_id=api_id) if bookmakers else None
        readiness = assess_ecse_readiness(conn, api_id, normalized=normalized) if normalized else {
            "has_1x2": False,
            "has_ou25": False,
            "has_btts": False,
            "lambda_inputs_available": False,
            "ecse_ready": False,
        }

        rows.append(
            {
                "api_football_fixture_id": api_id,
                "sportmonks_fixture_id": sm_id,
                "competition_key": item["competition_key"],
                "crosswalk_confidence": item.get("combined_confidence"),
                "odds_source": source,
                "raw_odds_path": raw_path,
                "bookmaker_count": normalized.bookmaker_count if normalized else 0,
                "has_1x2": readiness["has_1x2"],
                "has_ou25": readiness["has_ou25"],
                "has_btts": readiness["has_btts"],
                "has_ou15": bool(normalized and normalized.over_under_1_5),
                "has_ou35": bool(normalized and normalized.over_under_3_5),
                "has_correct_score": bool(normalized and normalized.has_correct_score),
                "has_double_chance": bool(normalized and normalized.has_double_chance),
                "ECSE_ready": readiness.get("ecse_ready", False),
                "missing_markets": list(normalized.missing_markets) if normalized else ["all"],
            }
        )

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now_iso(),
        "accepted_crosswalk_count": len(accepted),
        "fixtures_scanned": len(rows),
        "fixtures_with_odds": sum(1 for r in rows if r["bookmaker_count"] > 0),
        "ecse_ready_count": sum(1 for r in rows if r["ECSE_ready"]),
        "api_calls_used": api_calls,
        "dry_run": dry_run,
        "fixtures": rows,
    }


def _append_log(log_path: Path, entry: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _probabilities_valid(normalized) -> bool:
    for probs in normalized.normalized_probabilities.values():
        if not isinstance(probs, dict):
            continue
        for v in probs.values():
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v) or v < 0 or v > 1)):
                return False
    return True


@dataclass
class SportmonksOddsImportResult:
    phase: str = PHASE
    dry_run: bool = False
    crosswalk_accepted: int = 0
    imported_count: int = 0
    api_calls_used: int = 0
    cache_hits: int = 0
    ecse_ready_count: int = 0
    skipped: list[dict[str, Any]] = field(default_factory=list)
    imported: list[dict[str, Any]] = field(default_factory=list)
    provider_errors: list[dict[str, Any]] = field(default_factory=list)
    log_path: str | None = None


def import_sportmonks_uefa_odds(
    repo: FootballIntelligenceRepository,
    crosswalk: dict[str, Any],
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
    max_api_calls: int = 100,
    cache_first: bool = True,
    only_missing: bool = True,
    force: bool = False,
    log_path: Path | None = None,
) -> SportmonksOddsImportResult:
    settings = settings or get_settings()
    conn = repo._conn
    conn.execute("PRAGMA busy_timeout = 60000")
    result = SportmonksOddsImportResult(dry_run=dry_run)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = log_path or Path("logs") / f"euro_c2_sportmonks_odds_import_{stamp}.jsonl"
    result.log_path = str(log_file)
    raw_dir = Path("artifacts/euro_c2/raw_sportmonks_odds")
    raw_dir.mkdir(parents=True, exist_ok=True)

    accepted = [m for m in crosswalk.get("accepted") or [] if m.get("accepted")]
    result.crosswalk_accepted = len(accepted)

    sm_rows = {
        int(r["provider_fixture_id"]): r
        for r in _load_sportmonks_feed_rows(
            conn,
            competition_keys=list({m["competition_key"] for m in accepted} or UEFA_CUP_KEYS),
            days_ahead=30,
        )
    }

    api_calls = 0
    for item in accepted:
        api_id = int(item["api_football_fixture_id"])
        sm_id = int(item["sportmonks_fixture_id"])
        comp = str(item["competition_key"])
        confidence = float(item.get("combined_confidence") or 0)
        entry_base = {
            "phase": PHASE,
            "api_football_fixture_id": api_id,
            "sportmonks_fixture_id": sm_id,
            "competition_key": comp,
            "crosswalk_confidence": confidence,
            "dry_run": dry_run,
        }

        if item.get("ambiguous") or confidence < MIN_CROSSWALK_CONFIDENCE:
            result.skipped.append({**entry_base, "reason": "crosswalk_rejected"})
            _append_log(log_file, {**entry_base, "action": "skip", "reason": "crosswalk_rejected"})
            continue

        existing = _latest_odds_snapshot(conn, api_id)
        if existing and not is_fake_odds_payload(existing["payload"]) and only_missing and not force:
            existing_norm = normalize_uefa_odds_snapshot(existing["payload"], fixture_id=api_id)
            if _markets_complete(existing_norm):
                result.skipped.append({**entry_base, "reason": "already_has_required_markets"})
                _append_log(log_file, {**entry_base, "action": "skip", "reason": "already_has_required_markets"})
                continue

        sm_row = sm_rows.get(sm_id)
        fixture_data, source, raw_path = (None, "none", None)
        if cache_first:
            fixture_data, source, raw_path = load_sportmonks_odds_payload(
                conn, sm_id, settings=settings, sm_row=sm_row
            )
            if fixture_data:
                result.cache_hits += 1
                _append_log(log_file, {**entry_base, "action": "cache_hit", "source": source})

        if not fixture_data and api_calls < max_api_calls:
            if dry_run:
                source = "would_fetch_live"
                api_calls += 1
                result.api_calls_used = api_calls
                _append_log(log_file, {**entry_base, "action": "dry_run_api_call"})
            else:
                fixture_data, source, raw_path = fetch_sportmonks_odds_live(sm_id, settings=settings)
                api_calls += 1
                result.api_calls_used = api_calls
                _append_log(
                    log_file,
                    {**entry_base, "action": "api_call", "source": source, "ok": fixture_data is not None},
                )
        elif not fixture_data:
            result.skipped.append({**entry_base, "reason": "max_api_calls_reached"})
            _append_log(log_file, {**entry_base, "action": "skip", "reason": "max_api_calls_reached"})
            continue

        if dry_run and source == "would_fetch_live":
            result.imported.append({**entry_base, "action": "would_import"})
            continue

        if not fixture_data:
            result.skipped.append({**entry_base, "reason": "no_sportmonks_odds"})
            result.provider_errors.append({**entry_base, "error": "no_sportmonks_odds"})
            continue

        bookmakers = fixture_data_to_bookmakers(fixture_data)
        if not bookmakers:
            result.skipped.append({**entry_base, "reason": "unparseable_sportmonks_odds"})
            continue

        if not raw_path and not dry_run:
            raw_path = str(raw_dir / f"{sm_id}_{stamp}.json")
            Path(raw_path).write_text(
                json.dumps(
                    {
                        "api_football_fixture_id": api_id,
                        "sportmonks_fixture_id": sm_id,
                        "fetched_at": _utc_now_iso(),
                        "source": source,
                        "fixture_data": fixture_data,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        normalized = normalize_uefa_odds_snapshot(bookmakers, fixture_id=api_id, raw_odds_path=raw_path)
        if not _probabilities_valid(normalized):
            result.skipped.append({**entry_base, "reason": "invalid_probabilities"})
            continue
        if not normalized.match_winner and not normalized.over_under_2_5:
            result.skipped.append({**entry_base, "reason": "missing_core_markets"})
            continue

        if existing and not force:
            incoming_at = _utc_now_iso()
            if _existing_is_newer_than(existing.get("snapshot_at"), incoming_at):
                result.skipped.append({**entry_base, "reason": "newer_snapshot_exists"})
                continue

        payload = {
            "snapshot_at": _utc_now_iso(),
            "source": "euro_c2_sportmonks_import",
            "provider": "sportmonks",
            "phase": PHASE,
            "api_call_source": source,
            "api_football_fixture_id": api_id,
            "sportmonks_fixture_id": sm_id,
            "crosswalk_confidence": confidence,
            "bookmakers": bookmakers,
            "normalized": normalized.to_dict(),
            "raw_odds_path": raw_path,
        }

        if dry_run:
            result.imported.append(
                {
                    **entry_base,
                    "action": "would_import",
                    "bookmaker_count": normalized.bookmaker_count,
                    "overround_1x2": normalized.overround_1x2,
                }
            )
            continue

        repo.save_snapshot(
            "odds_snapshots",
            fixture_id=api_id,
            competition_key=comp,
            payload=payload,
            snapshot_at=payload["snapshot_at"],
        )
        result.imported_count += 1
        result.imported.append({**entry_base, "action": "imported", "snapshot_at": payload["snapshot_at"]})
        _append_log(log_file, {**entry_base, "action": "imported"})

    readiness_rows: list[dict[str, Any]] = []
    for item in accepted:
        api_id = int(item["api_football_fixture_id"])
        snap = _latest_odds_snapshot(conn, api_id) if not dry_run else None
        norm = None
        if snap and not is_fake_odds_payload(snap["payload"]):
            norm = normalize_uefa_odds_snapshot(snap["payload"], fixture_id=api_id)
        readiness = assess_ecse_readiness(conn, api_id, normalized=norm)
        if readiness.get("ecse_ready"):
            result.ecse_ready_count += 1
        readiness_rows.append(
            {
                "fixture_id": api_id,
                "sportmonks_fixture_id": item.get("sportmonks_fixture_id"),
                "competition_key": item.get("competition_key"),
                "has_1x2": readiness["has_1x2"],
                "has_ou25": readiness["has_ou25"],
                "has_btts": readiness["has_btts"],
                "has_required_lambda_inputs": readiness["lambda_inputs_available"],
                "source_provider": "sportmonks" if readiness["has_1x2"] or readiness["has_ou25"] else None,
                "odds_timestamp": snap["snapshot_at"] if snap else None,
                "ECSE_ready": readiness["ecse_ready"],
                "missing_fields": readiness.get("blockers") or [],
                "crosswalk_confidence": item.get("combined_confidence"),
            }
        )

    return result, readiness_rows


def build_ecse_readiness_artifact(readiness_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now_iso(),
        "fixtures": readiness_rows,
        "ecse_ready_count": sum(1 for r in readiness_rows if r.get("ECSE_ready")),
        "partial_count": sum(
            1 for r in readiness_rows if (r.get("has_1x2") or r.get("has_ou25")) and not r.get("ECSE_ready")
        ),
    }


def final_recommendation(
    crosswalk: dict[str, Any],
    scan: dict[str, Any],
    import_result: SportmonksOddsImportResult,
    *,
    dry_run: bool = False,
) -> str:
    accepted = int(crosswalk.get("accepted_count") or 0)
    if accepted == 0:
        return "NEED_TEAM_MAPPING_FIX"
    if int(crosswalk.get("ambiguous_count") or 0) > accepted * 0.2:
        return "NEED_PROVIDER_CROSSWALK_REVIEW"

    ready = import_result.ecse_ready_count or int(scan.get("ecse_ready_count") or 0)
    with_odds = int(scan.get("fixtures_with_odds") or 0)
    targeted = max(1, accepted)

    if ready > 0 and ready / targeted >= 0.8:
        return "SPORTMONKS_ODDS_READY_FOR_ECSE"
    if ready > 0:
        return "PARTIAL_SPORTMONKS_ODDS_READY"
    if with_odds > 0 or import_result.imported_count > 0:
        return "PARTIAL_SPORTMONKS_ODDS_READY"
    if with_odds == 0 and import_result.api_calls_used >= max(1, import_result.crosswalk_accepted // 2):
        return "NO_SPORTMONKS_ODDS_AVAILABLE"
    if dry_run:
        return "DO_NOT_RUN_ECSE_YET"
    return "DO_NOT_RUN_ECSE_YET"
