"""Phase 53 — API-Sports deep data fetch, normalize, and merge (additive only)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.clients.api_response import ApiCallResult
from worldcup_predictor.config.competitions import CompetitionConfig
from worldcup_predictor.domain.fixture import Fixture
from worldcup_predictor.domain.intelligence import ApiInspectionReport, EndpointInspection, MatchIntelligenceReport
from worldcup_predictor.integrations.player_feature_extraction import (
    compute_conservative_player_score,
    enrich_fixture_player_row,
    enrich_topscorer_row,
    rating_trend,
    team_chance_creation_aggregate,
)
from worldcup_predictor.prediction.player_position_utils import is_goalkeeper, normalize_position
from worldcup_predictor.schedule.match_center import FINISHED_STATUSES

API_SPORTS_DEEP_KEY = "api_sports_deep"


def _log_endpoint(
    log: list[EndpointInspection],
    endpoint: str,
    result: ApiCallResult,
) -> None:
    count = len(result.data) if isinstance(result.data, list) else (1 if result.data else 0)
    status = "loaded" if result.ok and count else ("error" if result.error else "empty")
    log.append(
        EndpointInspection(
            endpoint=endpoint,
            loaded=bool(result.ok and count),
            response_count=count,
            source=result.source,
            error=result.error,
            status=status,
        )
    )


def _int_val(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_val(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.replace("%", "").strip()
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_top_scorers(raw: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block in raw:
        if not isinstance(block, dict):
            continue
        # API format A — flat {player, statistics[]}
        if block.get("player") and block.get("statistics") is not None:
            _append_topscorer_rows(rows, block.get("player"), block.get("statistics"))
            continue
        # API format B — nested {team, players[]}
        team = block.get("team") or {}
        team_name = str(team.get("name") or "")
        team_id = team.get("id")
        for entry in block.get("players") or []:
            if not isinstance(entry, dict):
                continue
            player = entry.get("player") or entry
            stats_raw = entry.get("statistics")
            if stats_raw is None:
                stats_raw = [entry.get("statistics") or {}]
            elif isinstance(stats_raw, dict):
                stats_raw = [stats_raw]
            _append_topscorer_rows(
                rows,
                player if isinstance(player, dict) else {"name": str(entry.get("name") or "")},
                stats_raw,
                default_team_name=team_name,
                default_team_id=team_id,
            )
    rows.sort(key=lambda r: (r.get("goals") or 0), reverse=True)
    return rows


def _append_topscorer_rows(
    rows: list[dict[str, Any]],
    player: Any,
    statistics: Any,
    *,
    default_team_name: str = "",
    default_team_id: Any = None,
) -> None:
    if not isinstance(player, dict):
        return
    name = str(player.get("name") or "")
    if not name:
        return
    stats_list = statistics if isinstance(statistics, list) else []
    if isinstance(statistics, dict):
        stats_list = [statistics]
    if not stats_list:
        stats_list = [{}]
    for stats in stats_list:
        if not isinstance(stats, dict):
            continue
        team = stats.get("team") or {}
        team_name = str(team.get("name") or default_team_name or "")
        team_id = team.get("id") if team.get("id") is not None else default_team_id
        games = stats.get("games") or {}
        goals_block = stats.get("goals") or {}
        position = str(games.get("position") or player.get("position") or stats.get("position") or "")
        goals = _int_val(goals_block.get("total") if isinstance(goals_block, dict) else goals_block) or 0
        assists = _int_val((stats.get("goals") or {}).get("assists") if isinstance(stats.get("goals"), dict) else None) or 0
        if is_goalkeeper(position):
            continue
        base = {
            "player": name,
            "team": team_name,
            "team_id": team_id,
            "position": normalize_position(position),
            "goals": goals,
            "assists": assists,
            "data_source": "api_sports_topscorers",
        }
        rows.append(enrich_topscorer_row(stats, games, base))


def normalize_fixture_players(raw: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for team_block in raw:
        if not isinstance(team_block, dict):
            continue
        team = team_block.get("team") or {}
        team_name = str(team.get("name") or "")
        for entry in team_block.get("players") or []:
            if not isinstance(entry, dict):
                continue
            player = entry.get("player") or {}
            name = str(player.get("name") or "")
            if not name:
                continue
            stats_list = entry.get("statistics") or []
            stats = stats_list[0] if stats_list and isinstance(stats_list[0], dict) else {}
            games = stats.get("games") or {} if isinstance(stats, dict) else {}
            position = str(games.get("position") or player.get("pos") or "")
            if is_goalkeeper(position):
                continue
            goals_block = stats.get("goals") or {} if isinstance(stats, dict) else {}
            goals = _int_val(goals_block.get("total") if isinstance(goals_block, dict) else None) or 0
            shots = _int_val((stats.get("shots") or {}).get("total") if isinstance(stats.get("shots"), dict) else None) or 0
            base = {
                "player": name,
                "team": team_name,
                "position": normalize_position(position),
                "goals": goals,
                "shots": shots,
                "data_source": "api_sports_fixture_players",
            }
            row = enrich_fixture_player_row(stats, games, base)
            avg_rating = _float_val(row.get("average_rating"))
            fixture_rating = _float_val(row.get("player_rating"))
            trend = rating_trend(fixture_rating, avg_rating)
            if trend:
                row["recent_rating_trend"] = trend
            rows.append(row)
    return rows


def normalize_squad(raw: list[Any], *, team_id: int, team_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block in raw:
        if not isinstance(block, dict):
            continue
        for entry in block.get("players") or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "")
            if not name:
                continue
            position = str(entry.get("position") or "")
            rows.append(
                {
                    "name": name,
                    "team_id": team_id,
                    "team_name": team_name,
                    "position": normalize_position(position),
                    "age": entry.get("age"),
                    "data_source": "api_sports_squads",
                }
            )
    return rows


def normalize_predictions(raw: list[Any]) -> dict[str, Any]:
    if not raw:
        return {"available": False}
    block = raw[0] if isinstance(raw[0], dict) else {}
    preds_raw = block.get("predictions")
    if isinstance(preds_raw, list) and preds_raw:
        pred = preds_raw[0] if isinstance(preds_raw[0], dict) else {}
    elif isinstance(preds_raw, dict):
        pred = preds_raw
    else:
        pred = block.get("prediction") if isinstance(block.get("prediction"), dict) else block
    if not isinstance(pred, dict):
        return {"available": False}

    percent = pred.get("percent") or {}
    home_pct = _float_val(percent.get("home"))
    draw_pct = _float_val(percent.get("draw"))
    away_pct = _float_val(percent.get("away"))

    winner = pred.get("winner") or {}
    winner_name = str(winner.get("name") or "") if isinstance(winner, dict) else ""
    advice = str(pred.get("advice") or block.get("advice") or "")

    lean = "draw"
    best = draw_pct or 0
    if (home_pct or 0) >= best:
        lean, best = "home_win", home_pct or 0
    if (away_pct or 0) >= best:
        lean, best = "away_win", away_pct or 0

    under_over = str(pred.get("under_over") or pred.get("goals") or "")

    return {
        "available": bool(home_pct or draw_pct or away_pct or winner_name or advice),
        "home_win_pct": home_pct,
        "draw_pct": draw_pct,
        "away_win_pct": away_pct,
        "winner_name": winner_name,
        "advice": advice,
        "under_over_hint": under_over,
        "api_one_x_two_lean": lean,
        "disclaimer": "API-Football prediction is external reference only — never overrides model output.",
    }


def compute_prediction_agreement(model_selection: str, api_ref: dict[str, Any]) -> dict[str, Any]:
    if not api_ref.get("available"):
        return {"available": False}
    api_lean = str(api_ref.get("api_one_x_two_lean") or "draw")
    model = model_selection or "draw"
    if model == api_lean:
        agreement = 100.0
    elif model == "draw" or api_lean == "draw":
        agreement = 55.0
    elif {model, api_lean} == {"home_win", "away_win"}:
        agreement = 0.0
    else:
        agreement = 35.0
    return {
        "available": True,
        "model_one_x_two": model,
        "api_one_x_two_lean": api_lean,
        "agreement_pct": round(agreement, 1),
        "home_win_pct": api_ref.get("home_win_pct"),
        "draw_pct": api_ref.get("draw_pct"),
        "away_win_pct": api_ref.get("away_win_pct"),
        "advice": api_ref.get("advice"),
        "disclaimer": api_ref.get("disclaimer"),
    }


def _fixture_players_ttl(status: str | None) -> int:
    code = (status or "NS").upper()
    if code in FINISHED_STATUSES:
        return 43200
    return 1800


def attach_api_sports_deep_data(
    report: MatchIntelligenceReport,
    api: ApiFootballClient,
    competition: CompetitionConfig,
) -> MatchIntelligenceReport:
    """Fetch Phase 53 endpoints and merge into supplemental_sources — never raises."""
    if not api.is_configured:
        return report

    fixture = report.fixture
    if fixture is None:
        return report

    endpoint_log = list(report.api_inspection.endpoints if report.api_inspection else [])
    supplemental = dict(report.supplemental_sources or {})
    deep: dict[str, Any] = dict(supplemental.get(API_SPORTS_DEEP_KEY) or {})

    ts_result = api.get_top_scorers(competition.league_id, competition.season)
    _log_endpoint(endpoint_log, "players/topscorers", ts_result)
    if ts_result.ok and isinstance(ts_result.data, list) and ts_result.data:
        deep["top_scorers"] = normalize_top_scorers(ts_result.data)

    fp_ttl = _fixture_players_ttl(fixture.status)
    fp_result = api.get_fixture_players(fixture.id, ttl_seconds=fp_ttl)
    _log_endpoint(endpoint_log, "fixtures/players", fp_result)
    if fp_result.ok and isinstance(fp_result.data, list) and fp_result.data:
        deep["fixture_players"] = normalize_fixture_players(fp_result.data)

    squads: dict[str, Any] = {}
    for side, team_id, team_name in (
        ("home", fixture.home_team_id, fixture.home_team),
        ("away", fixture.away_team_id, fixture.away_team),
    ):
        if not team_id:
            continue
        sq_result = api.get_team_squad(int(team_id))
        _log_endpoint(endpoint_log, f"players/squads/{side}", sq_result)
        if sq_result.ok and isinstance(sq_result.data, list) and sq_result.data:
            squads[side] = normalize_squad(sq_result.data, team_id=int(team_id), team_name=team_name)
    if squads:
        deep["squads"] = squads

    team_creation: dict[str, Any] = {}
    for side, team_name in (("home", fixture.home_team), ("away", fixture.away_team)):
        fp_rows = [r for r in deep.get("fixture_players") or [] if str(r.get("team", "")).lower() == team_name.lower()]
        ts_rows = [r for r in deep.get("top_scorers") or [] if str(r.get("team", "")).lower() == team_name.lower()]
        combined = fp_rows or ts_rows
        if combined:
            team_creation[side] = team_chance_creation_aggregate(combined)
    if team_creation:
        deep["chance_creation"] = team_creation

    pred_result = api.get_predictions(fixture.id)
    _log_endpoint(endpoint_log, "predictions", pred_result)
    if pred_result.ok and isinstance(pred_result.data, list):
        normalized = normalize_predictions(pred_result.data)
        if normalized.get("available"):
            deep["predictions_reference"] = normalized
        elif pred_result.error:
            deep["predictions_reference"] = {"available": False, "error": pred_result.error}

    if deep:
        supplemental[API_SPORTS_DEEP_KEY] = deep
        enrichment = list(report.enrichment_sources or [])
        if "api_sports_deep" not in enrichment:
            enrichment.append("api_sports_deep")

        draft = replace(
            report,
            supplemental_sources=supplemental,
            enrichment_sources=enrichment,
            api_inspection=ApiInspectionReport(endpoints=endpoint_log),
        )
        from worldcup_predictor.squad.squad_intelligence_engine import build_squad_intelligence_bundle

        squad_intel = build_squad_intelligence_bundle(draft)
        if squad_intel.get("available"):
            deep["squad_intelligence"] = squad_intel
            supplemental[API_SPORTS_DEEP_KEY] = deep
            draft = replace(draft, supplemental_sources=supplemental)
        return draft

    if endpoint_log != (report.api_inspection.endpoints if report.api_inspection else []):
        return replace(report, api_inspection=ApiInspectionReport(endpoints=endpoint_log))
    return report


def deep_player_rows_for_team(report: MatchIntelligenceReport, team_name: str) -> list[dict[str, Any]]:
    """Unified player rows for a team from API-Sports deep bundle."""
    deep = (getattr(report, "supplemental_sources", None) or {}).get(API_SPORTS_DEEP_KEY) or {}
    needle = team_name.lower()
    rows: list[dict[str, Any]] = []

    for row in deep.get("top_scorers") or []:
        if isinstance(row, dict) and str(row.get("team", "")).lower() == needle:
            rows.append({**row, "score_hint": compute_conservative_player_score(row)})

    for row in deep.get("fixture_players") or []:
        if isinstance(row, dict) and str(row.get("team", "")).lower() == needle:
            rows.append({**row, "score_hint": compute_conservative_player_score(row)})

    home_name = report.home_team.team_name.lower()
    away_name = report.away_team.team_name.lower()
    squads = deep.get("squads") or {}
    if isinstance(squads, dict):
        for side, players in squads.items():
            if not isinstance(players, list):
                continue
            side_team = home_name if side == "home" else away_name if side == "away" else ""
            if side_team != needle:
                continue
            for entry in players:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name") or "")
                position = str(entry.get("position") or "")
                if not name or is_goalkeeper(position):
                    continue
                pos_lower = position.lower()
                if "attack" in pos_lower or pos_lower in {"f", "fw", "st", "cf"}:
                    hint = 52.0
                elif "mid" in pos_lower or pos_lower in {"m", "cm", "am", "dm"}:
                    hint = 47.0
                else:
                    hint = 42.0
                squad_row = {
                    "player": name,
                    "team": str(entry.get("team_name") or team_name),
                    "position": normalize_position(position),
                    "data_source": "api_sports_squads",
                    "goals": 0,
                    "score_hint": hint,
                }
                rows.append(squad_row)

    return rows


def build_api_sports_explainability_context(
    report: MatchIntelligenceReport | None,
    prediction: Any | None,
) -> dict[str, Any]:
    if report is None:
        return {}
    deep = (getattr(report, "supplemental_sources", None) or {}).get(API_SPORTS_DEEP_KEY) or {}
    ctx: dict[str, Any] = {}

    tops = deep.get("top_scorers") or []
    if tops:
        ctx["top_scorers_sample"] = tops[:5]
        ctx["top_scorers_available"] = True

    fp = deep.get("fixture_players") or []
    if fp:
        ctx["fixture_players_count"] = len(fp)
        ctx["fixture_players_available"] = True

    api_pred = deep.get("predictions_reference") or {}
    if api_pred.get("available") and prediction is not None:
        ctx["api_football_prediction"] = compute_prediction_agreement(
            getattr(getattr(prediction, "one_x_two", None), "selection", "draw"),
            api_pred,
        )

    squads = deep.get("squads") or {}
    if squads:
        ctx["squad_depth"] = {
            side: len(players) for side, players in squads.items() if isinstance(players, list)
        }

    squad_intel = deep.get("squad_intelligence") or {}
    if squad_intel.get("available"):
        ctx["squad_intelligence"] = squad_intel
        for side in ("home", "away"):
            side_data = squad_intel.get(side) or {}
            age = side_data.get("squad_age_profile") or {}
            depth = side_data.get("bench_depth") or {}
            if age.get("available"):
                ctx[f"{side}_experience_score"] = age.get("experience_score")
                ctx[f"{side}_average_age"] = age.get("average_age")
            if depth.get("available"):
                ctx[f"{side}_bench_depth_score"] = depth.get("effective_depth_score")

    creation = deep.get("chance_creation") or {}
    if creation:
        ctx["chance_creation"] = creation

    rated = []
    for row in (deep.get("fixture_players") or [])[:8]:
        if isinstance(row, dict) and row.get("player_rating") is not None:
            rated.append(
                {
                    "player": row.get("player"),
                    "team": row.get("team"),
                    "rating": row.get("player_rating"),
                    "assists": row.get("assists"),
                    "key_passes": row.get("key_passes"),
                }
            )
    if rated:
        ctx["player_ratings_sample"] = rated

    return ctx


def parse_live_fixtures(
    raw: list[Any],
    competition_key: str,
    api: ApiFootballClient,
) -> list[Any]:
    """Parse live API fixtures into Fixture objects."""
    from worldcup_predictor.domain.fixture import Fixture

    fixtures: list[Fixture] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            fixtures.append(api.parse_fixture_item(item, competition_key=competition_key))
        except Exception:
            continue
    return fixtures
