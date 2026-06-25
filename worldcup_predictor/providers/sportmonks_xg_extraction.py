"""Phase 32A — cache-first Sportmonks xG Match extraction (expose only, no WDE)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.providers.sportmonks_enrichment import (
    WORLD_CUP_2026_COMPETITION_KEY,
    _fixture_data_from_cache_row,
    _is_world_cup_fixture,
    fetch_worldcup_fixture_enrichment,
    resolve_unified_worldcup_fixture_intelligence,
)
from worldcup_predictor.providers.sportmonks_provider import (
    WORLD_CUP_2026_LEAGUE_ID,
    SportmonksProvider,
)
from worldcup_predictor.quota.cache_policy import DAILY_TTL_SECONDS, MATCH_TTL_SECONDS

logger = logging.getLogger(__name__)

# Sportmonks XG Match component — nested includes per dashboard reference.
XG_MATCH_FIXTURE_INCLUDES: tuple[str, ...] = (
    "participants",
    "league",
    "venue",
    "state",
    "scores",
    "events.type",
    "events.period",
    "events.player",
    "xGFixture.type",
    "lineups.player",
    "lineups.xGLineup.type",
    "lineups.details.type",
)

# When xG add-on is not licensed — still parse statistics + lineups without premium includes.
XG_MATCH_FALLBACK_INCLUDES: tuple[str, ...] = (
    "participants",
    "league",
    "venue",
    "state",
    "scores",
    "statistics",
    "lineups",
    "lineups.details.type",
)

# Expected types — https://docs.sportmonks.com/v3/definitions/types/expected
_XG_TYPE_MAP: dict[int, str] = {
    5304: "xg",
    5305: "xgot",
    7939: "xpts",
    7940: "xg_penalties",
    7941: "xg_free_kicks",
    7942: "xg_corners",
    7943: "npxg",
    7944: "xg_set_play",
    7945: "xg_open_play",
    9684: "xgd",
    9685: "shooting_performance",
    9686: "xg_prevented",
    9687: "xga",
}

_XG_STORE_DIR = "xg_match"
_DASHBOARD_DEMO_FIXTURE_ID = 18882619  # Sportmonks blog EPL example (non-WC testing only)


@dataclass(frozen=True)
class SportmonksXgExtractionResult:
    success: bool
    source_chain: tuple[str, ...]
    sportmonks_fixture_id: int | None
    api_fixture_id: int | None
    endpoint_path: str
    includes: tuple[str, ...]
    api_calls_made: int
    raw_available: bool
    raw_json_size: int
    parsed: dict[str, Any]
    message: str
    configured: bool = True


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _include_string(includes: tuple[str, ...]) -> str:
    return ";".join(includes)


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().replace("%", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _type_id_from_row(row: dict[str, Any]) -> int | None:
    type_id = row.get("type_id")
    if type_id is not None:
        try:
            return int(type_id)
        except (TypeError, ValueError):
            pass
    type_block = row.get("type")
    if isinstance(type_block, dict) and type_block.get("id") is not None:
        try:
            return int(type_block["id"])
        except (TypeError, ValueError):
            return None
    return None


def _type_label_from_row(row: dict[str, Any]) -> str:
    type_block = row.get("type")
    if isinstance(type_block, dict):
        for key in ("developer_name", "code", "name"):
            text = type_block.get(key)
            if text:
                return str(text).lower()
    tid = _type_id_from_row(row)
    if tid is not None:
        return _XG_TYPE_MAP.get(tid, f"type_{tid}")
    return ""


def _value_from_row(row: dict[str, Any]) -> float | None:
    data = row.get("data")
    if isinstance(data, dict):
        val = _float_or_none(data.get("value"))
        if val is not None:
            return val
    return _float_or_none(row.get("value"))


def _expected_rows_from_fixture(raw: dict[str, Any]) -> list[dict[str, Any]]:
    from worldcup_predictor.feature_store.xg_discovery.xg_fixture_parser import expected_rows_from_fixture

    return expected_rows_from_fixture(raw)


def _metric_key_from_row(row: dict[str, Any]) -> str | None:
    from worldcup_predictor.feature_store.xg_discovery.xg_fixture_parser import classify_metric_key

    return classify_metric_key(row)


def _participant_side_map(raw: dict[str, Any]) -> dict[int, str]:
    out: dict[int, str] = {}
    for participant in _safe_list(raw.get("participants")):
        if not isinstance(participant, dict):
            continue
        meta = participant.get("meta") or {}
        loc = str(meta.get("location") or "").lower()
        if loc not in {"home", "away"}:
            continue
        try:
            out[int(participant["id"])] = loc
        except (TypeError, ValueError, KeyError):
            continue
    return out


def _statistics_xg_map(raw: dict[str, Any]) -> dict[str, float]:
    """Fallback xG from generic statistics include."""
    id_to_side = _participant_side_map(raw)
    xg_hints = frozenset({"expected goals", "expected_goals", "xg", "xgoals", "expected goals (xg)"})
    xg: dict[str, float] = {}
    for entry in _safe_list(raw.get("statistics")):
        if not isinstance(entry, dict):
            continue
        type_block = entry.get("type")
        label = ""
        if isinstance(type_block, dict):
            label = str(type_block.get("name") or type_block.get("developer_name") or "").lower()
        if not any(h in label for h in xg_hints):
            continue
        val = _value_from_row(entry)
        if val is None:
            continue
        try:
            participant_id = int(entry.get("participant_id"))
        except (TypeError, ValueError):
            continue
        side = id_to_side.get(participant_id)
        if side:
            xg[side] = val
    return xg


def _parse_team_xg_metrics(raw: dict[str, Any]) -> dict[str, Any]:
    id_to_side = _participant_side_map(raw)
    by_side: dict[str, dict[str, float]] = {"home": {}, "away": {}}
    raw_fixture_fields: list[dict[str, Any]] = []

    for row in _expected_rows_from_fixture(raw):
        metric = _metric_key_from_row(row)
        val = _value_from_row(row)
        if metric is None or val is None:
            continue
        loc = str(row.get("location") or "").lower()
        if loc not in by_side:
            try:
                pid = int(row.get("participant_id"))
                loc = id_to_side.get(pid, "")
            except (TypeError, ValueError):
                loc = ""
        if loc in by_side:
            by_side[loc][metric] = val
        raw_fixture_fields.append(
            {
                "metric": metric,
                "location": loc or None,
                "type_id": _type_id_from_row(row),
                "value": val,
            }
        )

    stats_xg = _statistics_xg_map(raw)
    source: Literal["xGFixture", "statistics", "none"] = "none"
    if by_side["home"] or by_side["away"]:
        source = "xGFixture"
    elif stats_xg:
        source = "statistics"
        for side, val in stats_xg.items():
            by_side.setdefault(side, {})["xg"] = val

    def _side_val(side: str, key: str) -> float | None:
        return by_side.get(side, {}).get(key)

    return {
        "home_xg": _side_val("home", "xg"),
        "away_xg": _side_val("away", "xg"),
        "home_xgot": _side_val("home", "xgot"),
        "away_xgot": _side_val("away", "xgot"),
        "home_xpts": _side_val("home", "xpts"),
        "away_xpts": _side_val("away", "xpts"),
        "home_xg_penalties": _side_val("home", "xg_penalties"),
        "away_xg_penalties": _side_val("away", "xg_penalties"),
        "home_xg_free_kicks": _side_val("home", "xg_free_kicks"),
        "away_xg_free_kicks": _side_val("away", "xg_free_kicks"),
        "team_metrics": by_side,
        "xg_fixture_fields": raw_fixture_fields,
        "statistics_xg_fallback": stats_xg,
        "source": source,
        "raw_xg_fixture_present": raw.get("xGFixture") is not None,
        "expected_row_count": len(_expected_rows_from_fixture(raw)),
    }


def _parse_player_xg_summary(raw: dict[str, Any]) -> dict[str, Any]:
    id_to_side = _participant_side_map(raw)
    players: list[dict[str, Any]] = []
    for lineup in _safe_list(raw.get("lineups")):
        if not isinstance(lineup, dict):
            continue
        player_id = lineup.get("player_id")
        player_name = lineup.get("player_name") or lineup.get("name")
        team_id = lineup.get("team_id") or lineup.get("participant_id")
        side = None
        if team_id is not None:
            try:
                side = id_to_side.get(int(team_id))
            except (TypeError, ValueError):
                side = None
        xg_rows = lineup.get("xGLineup") or lineup.get("xgLineup") or []
        if not isinstance(xg_rows, list):
            xg_rows = []
        metrics: dict[str, float] = {}
        for row in xg_rows:
            if not isinstance(row, dict):
                continue
            metric = _metric_key_from_row(row)
            val = _value_from_row(row)
            if metric is not None and val is not None:
                metrics[metric] = val
        if not metrics and not player_name:
            continue
        players.append(
            {
                "player_id": player_id,
                "player_name": player_name,
                "team_side": side,
                "metrics": metrics,
                "xg": metrics.get("xg"),
                "xgot": metrics.get("xgot"),
            }
        )
    top_xg = sorted(
        [p for p in players if p.get("xg") is not None],
        key=lambda p: float(p["xg"]),
        reverse=True,
    )[:5]
    return {
        "player_count": len(players),
        "players_with_xg": sum(1 for p in players if p.get("xg") is not None),
        "top_scorers_by_xg": top_xg,
        "players": players,
    }


def parse_sportmonks_xg_match(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Parse team + player xG from a Sportmonks fixture payload."""
    if not raw:
        return {
            "available": False,
            "source": "none",
            "team": {},
            "player_xg_summary": {"player_count": 0, "players_with_xg": 0, "top_scorers_by_xg": [], "players": []},
        }
    team = _parse_team_xg_metrics(raw)
    player = _parse_player_xg_summary(raw)
    available = (
        team.get("home_xg") is not None
        or team.get("away_xg") is not None
        or player.get("players_with_xg", 0) > 0
    )
    return {
        "available": available,
        "source": team.get("source") or "none",
        "team": team,
        "player_xg_summary": player,
        "sportmonks_fixture_id": raw.get("id"),
        "league_id": raw.get("league_id"),
    }


def build_sportmonks_xg_api_block(parsed: dict[str, Any] | None) -> dict[str, Any]:
    """Public API shape for predict responses — no WDE fields."""
    parsed = parsed or {}
    team = parsed.get("team") or {}
    player = parsed.get("player_xg_summary") or {}
    return {
        "available": bool(parsed.get("available")),
        "home_xg": team.get("home_xg"),
        "away_xg": team.get("away_xg"),
        "home_xgot": team.get("home_xgot"),
        "away_xgot": team.get("away_xgot"),
        "home_xpts": team.get("home_xpts"),
        "away_xpts": team.get("away_xpts"),
        "home_xg_penalties": team.get("home_xg_penalties"),
        "away_xg_penalties": team.get("away_xg_penalties"),
        "home_xg_free_kicks": team.get("home_xg_free_kicks"),
        "away_xg_free_kicks": team.get("away_xg_free_kicks"),
        "player_xg_summary": {
            "player_count": player.get("player_count", 0),
            "players_with_xg": player.get("players_with_xg", 0),
            "top_scorers_by_xg": player.get("top_scorers_by_xg") or [],
        },
        "source": "sportmonks",
        "data_source": team.get("source") or parsed.get("source") or "none",
        "raw_xg_fixture_present": team.get("raw_xg_fixture_present", False),
        "expected_row_count": team.get("expected_row_count", 0),
    }


def _xg_store_path(settings: Settings, sportmonks_fixture_id: int) -> Path:
    root = Path(settings.api_cache_dir) / "sportmonks" / _XG_STORE_DIR
    return root / f"{int(sportmonks_fixture_id)}.json"


def _load_xg_store(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    expires = payload.get("expires_at_utc")
    if expires:
        try:
            exp_dt = datetime.fromisoformat(str(expires))
            if _utc_now() > exp_dt:
                return None
        except ValueError:
            pass
    return payload if isinstance(payload, dict) else None


def save_xg_extraction_store(
    *,
    settings: Settings,
    sportmonks_fixture_id: int,
    api_fixture_id: int | None,
    raw_fixture: dict[str, Any],
    parsed: dict[str, Any],
    includes: tuple[str, ...],
    source_chain: tuple[str, ...],
    ttl_seconds: int | None = None,
) -> Path:
    path = _xg_store_path(settings, sportmonks_fixture_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fetched = _utc_now()
    ttl = ttl_seconds if ttl_seconds is not None else DAILY_TTL_SECONDS
    state = raw_fixture.get("state")
    short_name = ""
    if isinstance(state, dict):
        short_name = str(state.get("short_name") or "").upper()
    if short_name not in {"FT", "AET", "FT_PEN", "AWARDED"}:
        ttl = MATCH_TTL_SECONDS
    payload = {
        "sportmonks_fixture_id": sportmonks_fixture_id,
        "api_fixture_id": api_fixture_id,
        "fetched_at_utc": fetched.isoformat(),
        "expires_at_utc": (fetched + timedelta(seconds=ttl)).isoformat(),
        "endpoint": f"/fixtures/{sportmonks_fixture_id}",
        "includes": list(includes),
        "source_chain": list(source_chain),
        "raw_fixture": raw_fixture,
        "parsed": parsed,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _payload_has_xg_rich_includes(raw: dict[str, Any]) -> bool:
    if raw.get("xGFixture") is not None:
        return True
    for lineup in _safe_list(raw.get("lineups")):
        if isinstance(lineup, dict) and lineup.get("xGLineup"):
            return True
    return False


def _is_access_denied(status_code: int | None, error: str | None) -> bool:
    if status_code == 403:
        return True
    if error and "403" in error:
        return True
    return False


def _fetch_xg_match_from_api(
    provider: SportmonksProvider,
    sportmonks_fixture_id: int,
    *,
    allow_non_wc: bool,
) -> tuple[dict[str, Any] | None, int | None, str | None, tuple[str, ...], int]:
    endpoint = f"/fixtures/{int(sportmonks_fixture_id)}"
    api_calls = 0
    for includes in (XG_MATCH_FIXTURE_INCLUDES, XG_MATCH_FALLBACK_INCLUDES):
        api_calls += 1
        status_code, payload, error = provider.safe_get(
            endpoint,
            params={"include": _include_string(includes)},
        )
        if _is_access_denied(status_code, error) and includes is XG_MATCH_FIXTURE_INCLUDES:
            continue
        if error or not isinstance(payload, dict):
            return None, status_code, error or "empty Sportmonks response", includes, api_calls
        data = payload.get("data")
        if not isinstance(data, dict):
            return None, status_code, "Sportmonks response missing fixture data object.", includes, api_calls
        if not allow_non_wc and not _is_world_cup_fixture(data):
            league_id = data.get("league_id")
            return (
                None,
                status_code,
                f"Fixture league_id={league_id} is not World Cup {WORLD_CUP_2026_LEAGUE_ID}.",
                includes,
                api_calls,
            )
        msg = None
        if includes is XG_MATCH_FALLBACK_INCLUDES and _is_access_denied(status_code, error):
            msg = "xGFixture include denied (403) — using statistics fallback includes."
        return data, status_code, msg, includes, api_calls
    return None, 403, "xGFixture include denied (403) — no fallback payload.", XG_MATCH_FALLBACK_INCLUDES, api_calls


def extract_fixture_xg_match(
    *,
    api_fixture_id: int | None = None,
    sportmonks_fixture_id: int | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
    kickoff_date: str | None = None,
    settings: Settings | None = None,
    repo: FootballIntelligenceRepository | None = None,
    force_refresh: bool = False,
    allow_non_wc: bool = False,
) -> SportmonksXgExtractionResult:
    """
    Cache-first xG Match extraction — World Cup scope by default.

    Resolution order:
      1. xg_match file store (fresh)
      2. SQLite sportmonks_fixture_enrichment (if xG-rich payload)
      3. Unified WC fixture intelligence (cache-first enrichment path)
      4. Dedicated GET /fixtures/{id} with XG_MATCH_FIXTURE_INCLUDES (1 API call)
    """
    settings = settings or get_settings()
    provider = SportmonksProvider(settings)
    includes = XG_MATCH_FIXTURE_INCLUDES
    endpoint_path = f"/fixtures/{sportmonks_fixture_id or 'unknown'}"
    chain: list[str] = []
    api_calls = 0

    if not provider.is_configured:
        empty = parse_sportmonks_xg_match(None)
        return SportmonksXgExtractionResult(
            success=False,
            source_chain=("not_configured",),
            sportmonks_fixture_id=sportmonks_fixture_id,
            api_fixture_id=api_fixture_id,
            endpoint_path=endpoint_path,
            includes=includes,
            api_calls_made=0,
            raw_available=False,
            raw_json_size=0,
            parsed=empty,
            message="SPORTMONKS_API_TOKEN not configured.",
            configured=False,
        )

    repository = repo or FootballIntelligenceRepository(settings.sqlite_path or None)
    sm_id = int(sportmonks_fixture_id) if sportmonks_fixture_id else None

    if sm_id and not force_refresh:
        stored = _load_xg_store(_xg_store_path(settings, sm_id))
        if stored and isinstance(stored.get("raw_fixture"), dict):
            chain.append("xg_match_store")
            raw = stored["raw_fixture"]
            parsed = stored.get("parsed") or parse_sportmonks_xg_match(raw)
            return SportmonksXgExtractionResult(
                success=True,
                source_chain=tuple(chain),
                sportmonks_fixture_id=sm_id,
                api_fixture_id=stored.get("api_fixture_id") or api_fixture_id,
                endpoint_path=str(stored.get("endpoint") or endpoint_path),
                includes=tuple(stored.get("includes") or includes),
                api_calls_made=0,
                raw_available=True,
                raw_json_size=len(json.dumps(raw, ensure_ascii=False)),
                parsed=parsed,
                message="Loaded xG extraction from file store.",
            )

    raw: dict[str, Any] | None = None

    if api_fixture_id is not None and not force_refresh:
        row = repository.get_sportmonks_fixture_enrichment_by_api_fixture_id(int(api_fixture_id))
        if row:
            fixture = _fixture_data_from_cache_row(row)
            sm_from_row = int(row.get("sportmonks_fixture_id") or 0) or None
            if fixture and sm_from_row:
                sm_id = sm_id or sm_from_row
                endpoint_path = f"/fixtures/{sm_id}"
                if _payload_has_xg_rich_includes(fixture) or parse_sportmonks_xg_match(fixture).get("available"):
                    chain.append("sqlite_enrichment_cache")
                    raw = fixture

    if raw is None and api_fixture_id is not None and home_team and away_team:
        unified = resolve_unified_worldcup_fixture_intelligence(
            api_fixture_id=int(api_fixture_id),
            home_team=home_team,
            away_team=away_team,
            kickoff_date=kickoff_date,
            competition_key=WORLD_CUP_2026_COMPETITION_KEY,
            settings=settings,
            repo=repository,
            force_refresh=force_refresh,
        )
        api_calls += unified.api_calls_made
        if unified.fixture:
            sm_id = sm_id or unified.sportmonks_fixture_id
            endpoint_path = unified.enrichment_endpoint or endpoint_path
            if _payload_has_xg_rich_includes(unified.fixture) or parse_sportmonks_xg_match(unified.fixture).get("available"):
                chain.append("unified_enrichment")
                raw = unified.fixture
            elif not chain:
                chain.extend(unified.source_chain)

    if raw is None and sm_id is not None:
        if not force_refresh:
            cached = repository.get_sportmonks_fixture_enrichment_cache(sm_id)
            if cached:
                fixture = _fixture_data_from_cache_row(cached)
                if fixture:
                    chain.append("sqlite_sm_id_cache")
                    raw = fixture

        if raw is None or force_refresh or not _payload_has_xg_rich_includes(raw):
            fetched, status, err, used_includes, fetch_calls = _fetch_xg_match_from_api(
                provider,
                sm_id,
                allow_non_wc=allow_non_wc,
            )
            api_calls += fetch_calls
            includes = used_includes
            if fetched is not None:
                chain.append("api_xg_match_includes" if used_includes is XG_MATCH_FIXTURE_INCLUDES else "api_xg_fallback_includes")
                raw = fetched
            elif err:
                parsed = parse_sportmonks_xg_match(raw)
                return SportmonksXgExtractionResult(
                    success=bool(raw),
                    source_chain=tuple(chain or ("api_failed",)),
                    sportmonks_fixture_id=sm_id,
                    api_fixture_id=api_fixture_id,
                    endpoint_path=f"/fixtures/{sm_id}",
                    includes=includes,
                    api_calls_made=api_calls,
                    raw_available=raw is not None,
                    raw_json_size=len(json.dumps(raw, ensure_ascii=False)) if raw else 0,
                    parsed=parsed,
                    message=err,
                )

    if raw is None and api_fixture_id is not None and home_team and away_team:
        enrich = fetch_worldcup_fixture_enrichment(
            sm_id or 0,
            fixture_id_api_football=api_fixture_id,
            settings=settings,
            repo=repository,
            force_refresh=force_refresh,
        )
        if enrich.fixture:
            sm_id = sm_id or enrich.sportmonks_fixture_id
            api_calls += enrich.api_calls_made
            chain.append("enrichment_fetch")
            raw = enrich.fixture
            endpoint_path = enrich.endpoint_path

    parsed = parse_sportmonks_xg_match(raw)
    raw_size = len(json.dumps(raw, ensure_ascii=False)) if raw else 0

    if raw and sm_id:
        save_xg_extraction_store(
            settings=settings,
            sportmonks_fixture_id=int(sm_id),
            api_fixture_id=api_fixture_id,
            raw_fixture=raw,
            parsed=parsed,
            includes=includes,
            source_chain=tuple(chain or ("parsed_only",)),
        )

    msg = "xG extraction complete."
    if not parsed.get("available"):
        msg = "Fixture payload loaded but no xG values present (pre-match or plan/add-on)."
    if not raw:
        msg = "No Sportmonks fixture payload resolved."

    return SportmonksXgExtractionResult(
        success=raw is not None,
        source_chain=tuple(chain or ("none",)),
        sportmonks_fixture_id=sm_id,
        api_fixture_id=api_fixture_id,
        endpoint_path=endpoint_path if sm_id else endpoint_path,
        includes=includes,
        api_calls_made=api_calls,
        raw_available=raw is not None,
        raw_json_size=raw_size,
        parsed=parsed,
        message=msg,
    )


def _report_kickoff_date(report: MatchIntelligenceReport) -> str | None:
    kickoff = getattr(report, "kickoff_utc", None)
    if kickoff is None and report.fixture is not None:
        kickoff = getattr(report.fixture, "kickoff_utc", None)
    if kickoff is None:
        return None
    return kickoff.date().isoformat()


def resolve_sportmonks_xg_from_report(
    report: MatchIntelligenceReport | None,
    *,
    settings: Settings | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Build API block from intelligence report — cache-first, no WDE."""
    settings = settings or get_settings()
    if report is None:
        return build_sportmonks_xg_api_block(None)

    supplemental = getattr(report, "supplemental_sources", None) or {}
    sm_block = supplemental.get("sportmonks_xg_match")
    if isinstance(sm_block, dict) and sm_block.get("parsed"):
        return build_sportmonks_xg_api_block(sm_block["parsed"])

    meta = report.provider_metadata or {}
    live = meta.get("sportmonks_fixture")
    if isinstance(live, dict) and live:
        parsed = parse_sportmonks_xg_match(live)
        if parsed.get("available"):
            return build_sportmonks_xg_api_block(parsed)

    kickoff = _report_kickoff_date(report)

    result = extract_fixture_xg_match(
        api_fixture_id=getattr(report, "fixture_id", None),
        home_team=report.home_team.team_name,
        away_team=report.away_team.team_name,
        kickoff_date=kickoff,
        settings=settings,
        force_refresh=force_refresh,
    )
    return build_sportmonks_xg_api_block(result.parsed)


def attach_sportmonks_xg_to_report(
    report: MatchIntelligenceReport,
    *,
    settings: Settings | None = None,
    force_refresh: bool = False,
) -> MatchIntelligenceReport:
    """Attach parsed xG to supplemental_sources — consumption only, no WDE."""
    settings = settings or get_settings()
    kickoff = _report_kickoff_date(report)
    extraction = extract_fixture_xg_match(
        api_fixture_id=getattr(report, "fixture_id", None),
        home_team=report.home_team.team_name,
        away_team=report.away_team.team_name,
        kickoff_date=kickoff,
        settings=settings,
        force_refresh=force_refresh,
    )
    supplemental = dict(report.supplemental_sources or {})
    supplemental["sportmonks_xg_match"] = {
        "parsed": extraction.parsed,
        "api_block": build_sportmonks_xg_api_block(extraction.parsed),
        "source_chain": list(extraction.source_chain),
        "endpoint": extraction.endpoint_path,
        "includes": list(extraction.includes),
        "api_calls_made": extraction.api_calls_made,
        "message": extraction.message,
    }
    report.supplemental_sources = supplemental
    return report


def attach_sportmonks_xg_to_prediction(
    prediction: MatchPrediction,
    report: MatchIntelligenceReport | None,
    *,
    settings: Settings | None = None,
) -> MatchPrediction:
    """Expose sportmonks_xg on prediction metadata for API output."""
    block = resolve_sportmonks_xg_from_report(report, settings=settings)
    prediction.metadata = dict(prediction.metadata or {})
    prediction.metadata["sportmonks_xg"] = json.dumps(block, ensure_ascii=False)
    return prediction


def load_sportmonks_xg_from_prediction(prediction: MatchPrediction) -> dict[str, Any] | None:
    raw = (prediction.metadata or {}).get("sportmonks_xg")
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return None


def extract_dashboard_demo_fixture(
    *,
    settings: Settings | None = None,
    force_refresh: bool = False,
) -> SportmonksXgExtractionResult:
    """Sportmonks blog/dashboard demo fixture — explicit non-WC test hook."""
    return extract_fixture_xg_match(
        sportmonks_fixture_id=_DASHBOARD_DEMO_FIXTURE_ID,
        settings=settings,
        force_refresh=force_refresh,
        allow_non_wc=True,
    )
