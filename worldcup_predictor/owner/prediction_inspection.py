"""Read-only owner prediction inspection — CLAUDE-OPS-1.

No provider calls. No DB writes. No prediction generation.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.owner_daily.fixture_discovery import resolve_target_date
from worldcup_predictor.owner_predict_eval.db_helpers import table_exists

Scope = Literal["stored", "evaluated", "pending", "all"]
OutputFormat = Literal["table", "json", "markdown"]
MarketFilter = Literal["1x2", "btts", "over_under", "correct_score", "first_goal", "goal_minute", "all"]

_SECRET_PATTERN = re.compile(
    r"(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+",
    re.IGNORECASE,
)

DB_MISSING_MSG = "PRODUCTION_DB_NOT_FOUND_OR_NOT_ACCESSIBLE"
NO_PREDICTIONS_MSG = "NO_STORED_PREDICTIONS_FOUND"


@dataclass
class InspectionConfig:
    date_arg: str = "today"
    timezone: str = "Europe/Vienna"
    scope: Scope = "all"
    limit: int = 50
    market: MarketFilter = "all"
    db_path: str | None = None


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _kickoff_on_local_date(kickoff_utc: str | None, target: date, tz_name: str) -> bool:
    dt = _parse_kickoff(kickoff_utc)
    if dt is None:
        return False
    local = dt.astimezone(ZoneInfo(tz_name))
    return local.date() == target


def _safe_json_load(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _redact_secrets(text: str) -> str:
    return _SECRET_PATTERN.sub(r"\1=***", text)


def _display_1x2(selection: str | None) -> str | None:
    if not selection:
        return None
    mapping = {
        "home_win": "1",
        "draw": "X",
        "away_win": "2",
        "home": "1",
        "away": "2",
        "1": "1",
        "x": "X",
        "2": "2",
    }
    return mapping.get(str(selection).lower().strip(), str(selection))


def _extract_markets(payload: dict[str, Any]) -> dict[str, Any]:
    one_x_two = payload.get("one_x_two") or {}
    over_under = payload.get("over_under") or {}
    detailed = payload.get("detailed_markets") or {}
    if not one_x_two and detailed.get("match_winner"):
        one_x_two = detailed["match_winner"]
    if not over_under and detailed.get("over_under_25"):
        over_under = detailed["over_under_25"]
    btts = (payload.get("extended_markets") or {}).get("btts") or detailed.get("btts") or {}
    scoreline = payload.get("scoreline") or {}
    goal_timing = payload.get("goal_timing") or detailed.get("goal_timing") or {}
    first_goal = payload.get("first_goal") or detailed.get("first_goal") or {}

    btts_pick = None
    if btts:
        if btts.get("selection"):
            btts_pick = str(btts.get("selection")).lower()
        else:
            yes = float(btts.get("yes") or btts.get("option_a") or btts.get("probability") or 0)
            btts_pick = "yes" if yes >= 0.5 else "no"

    predicted_scoreline = None
    if isinstance(scoreline, dict):
        predicted_scoreline = scoreline.get("label") or scoreline.get("top_1")
    elif scoreline:
        predicted_scoreline = str(scoreline)

    probs: dict[str, Any] = {}
    if one_x_two:
        probs["1x2"] = {
            k: one_x_two.get(k)
            for k in ("home", "draw", "away", "selection", "confidence", "probability")
            if one_x_two.get(k) is not None
        }
    if over_under:
        probs["over_under"] = {
            k: over_under.get(k)
            for k in ("selection", "over", "under", "confidence", "probability")
            if over_under.get(k) is not None
        }
    if btts:
        probs["btts"] = {k: btts.get(k) for k in ("yes", "no", "selection") if btts.get(k) is not None}
    if predicted_scoreline:
        probs["correct_score"] = {"top_1": predicted_scoreline}
        top3 = scoreline.get("top_3") if isinstance(scoreline, dict) else None
        if top3:
            probs["correct_score"]["top_3"] = top3
    if first_goal:
        probs["first_goal"] = first_goal if isinstance(first_goal, dict) else {"selection": first_goal}
    if goal_timing:
        probs["goal_minute"] = goal_timing if isinstance(goal_timing, dict) else {"selection": goal_timing}

    return {
        "main_pick_1x2": _display_1x2(one_x_two.get("selection")),
        "pick_btts": btts_pick,
        "pick_over_under": over_under.get("selection"),
        "predicted_scoreline": predicted_scoreline,
        "market_probabilities": probs,
    }


def _eval_outcome_label(row: dict[str, Any]) -> str:
    status = str(row.get("overall_status") or "").lower()
    if status in {"correct", "wrong", "partial", "unknown", "void"}:
        return status
    if row.get("final_score") or row.get("actual_result"):
        if status and status not in {"pending", "waiting_for_result"}:
            return status or "evaluated"
        return "pending"
    fixture_status = str(row.get("fixture_status") or "").upper()
    if fixture_status in {"FT", "AET", "PEN"}:
        return "pending" if not status else status
    return "pending"


def _matches_scope(scope: Scope, eval_row: dict[str, Any] | None, outcome: str) -> bool:
    if scope == "all" or scope == "stored":
        return True
    if scope == "evaluated":
        return outcome in {"correct", "wrong", "partial", "unknown", "void", "evaluated"}
    if scope == "pending":
        return outcome in {"pending", "waiting_for_result", ""}
    return True


def _matches_market(market: MarketFilter, markets: dict[str, Any]) -> bool:
    if market == "all":
        return True
    key_map = {
        "1x2": "main_pick_1x2",
        "btts": "pick_btts",
        "over_under": "pick_over_under",
        "correct_score": "predicted_scoreline",
        "first_goal": "first_goal",
        "goal_minute": "goal_minute",
    }
    field = key_map.get(market)
    if not field:
        return True
    if field in markets and markets.get(field):
        return True
    probs = markets.get("market_probabilities") or {}
    return market.replace("_", "") in str(probs).lower() or market in probs


def inspect_owner_predictions(config: InspectionConfig) -> dict[str, Any]:
    """Read stored predictions for a calendar date. Read-only."""
    db_path = get_db_path(config.db_path)
    if not db_path.exists() or db_path.stat().st_size == 0:
        return {
            "status": "error",
            "error": DB_MISSING_MSG,
            "db_path": str(db_path),
            "predictions": [],
        }

    target_date = resolve_target_date(config.date_arg, config.timezone)
    db_uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(db_uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if not table_exists(conn, "worldcup_stored_predictions"):
            return {
                "status": "error",
                "error": DB_MISSING_MSG,
                "detail": "worldcup_stored_predictions table missing",
                "predictions": [],
            }

        has_eval = table_exists(conn, "worldcup_prediction_evaluations")
        has_fixtures = table_exists(conn, "fixtures")
        has_results = table_exists(conn, "fixture_results")

        query = """
            SELECT
                sp.fixture_id,
                sp.competition_key,
                sp.kickoff_utc,
                sp.predicted_at,
                sp.source AS cache_source,
                sp.payload_json
        """
        if has_fixtures:
            query += ", f.home_team, f.away_team, f.status AS fixture_status"
        else:
            query += ", NULL AS home_team, NULL AS away_team, NULL AS fixture_status"
        if has_results:
            query += ", fr.final_score, fr.home_goals, fr.away_goals"
        else:
            query += ", NULL AS final_score, NULL AS home_goals, NULL AS away_goals"
        if has_eval:
            query += """,
                ev.overall_status,
                ev.final_score AS eval_final_score,
                ev.actual_result,
                ev.market_1x2_status,
                ev.market_btts_status,
                ev.market_ou_status,
                ev.market_fg_team_status,
                ev.market_goal_minute_status,
                ev.evaluated_at
            """
        else:
            query += """,
                NULL AS overall_status,
                NULL AS eval_final_score,
                NULL AS actual_result,
                NULL AS market_1x2_status,
                NULL AS market_btts_status,
                NULL AS market_ou_status,
                NULL AS market_fg_team_status,
                NULL AS market_goal_minute_status,
                NULL AS evaluated_at
            """
        query += """
            FROM worldcup_stored_predictions sp
        """
        active_filter = ""
        try:
            cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(worldcup_stored_predictions)").fetchall()}
            if "is_active" in cols:
                active_filter = " AND (sp.is_active IS NULL OR sp.is_active = 1)"
        except sqlite3.Error:
            pass
        if has_fixtures:
            query += " LEFT JOIN fixtures f ON f.fixture_id = sp.fixture_id"
        if has_results:
            query += " LEFT JOIN fixture_results fr ON fr.fixture_id = sp.fixture_id"
        if has_eval:
            query += " LEFT JOIN worldcup_prediction_evaluations ev ON ev.fixture_id = sp.fixture_id"
        query += """
            WHERE 1=1
        """ + active_filter + """
            ORDER BY sp.kickoff_utc ASC, sp.fixture_id ASC
        """

        rows = conn.execute(query).fetchall()
    finally:
        conn.close()

    items: list[dict[str, Any]] = []
    for row in rows:
        r = dict(row)
        kickoff = r.get("kickoff_utc")
        if not _kickoff_on_local_date(kickoff, target_date, config.timezone):
            continue

        payload = _safe_json_load(r.get("payload_json"))
        markets = _extract_markets(payload)
        outcome = _eval_outcome_label(r)

        if not _matches_scope(config.scope, r, outcome):
            continue
        if not _matches_market(config.market, markets):
            continue

        actual = r.get("eval_final_score") or r.get("final_score") or r.get("actual_result")
        confidence = payload.get("confidence_score") or payload.get("confidence")
        engine_version = (
            payload.get("prediction_engine_version")
            or payload.get("engine_version")
            or payload.get("pipeline_version")
        )

        item = {
            "fixture_id": r.get("fixture_id"),
            "kickoff_utc": kickoff,
            "kickoff_local_date": target_date.isoformat(),
            "competition": r.get("competition_key"),
            "home_team": r.get("home_team") or payload.get("home_team"),
            "away_team": r.get("away_team") or payload.get("away_team"),
            "prediction_status": "stored",
            "main_pick": markets.get("main_pick_1x2"),
            "confidence": confidence,
            "market_probabilities": markets.get("market_probabilities"),
            "predicted_scoreline": markets.get("predicted_scoreline"),
            "pick_btts": markets.get("pick_btts"),
            "pick_over_under": markets.get("pick_over_under"),
            "stored_at": r.get("predicted_at"),
            "actual_result": actual,
            "fixture_status": r.get("fixture_status"),
            "evaluation_status": r.get("overall_status"),
            "evaluation_outcome": outcome,
            "market_evaluations": {
                k: r.get(k)
                for k in (
                    "market_1x2_status",
                    "market_btts_status",
                    "market_ou_status",
                    "market_fg_team_status",
                    "market_goal_minute_status",
                )
                if r.get(k)
            },
            "evaluated_at": r.get("evaluated_at"),
            "cache_source": r.get("cache_source"),
            "prediction_engine_version": engine_version,
            "no_bet": bool(payload.get("no_bet_flag", False)),
        }
        items.append(item)
        if len(items) >= max(1, int(config.limit)):
            break

    if not items:
        return {
            "status": "empty",
            "error": NO_PREDICTIONS_MSG,
            "date": target_date.isoformat(),
            "timezone": config.timezone,
            "scope": config.scope,
            "predictions": [],
        }

    return {
        "status": "ok",
        "date": target_date.isoformat(),
        "timezone": config.timezone,
        "scope": config.scope,
        "market": config.market,
        "count": len(items),
        "predictions": items,
    }


def format_predictions_table(result: dict[str, Any]) -> str:
    if result.get("status") == "error":
        return str(result.get("error"))
    if result.get("status") == "empty":
        return NO_PREDICTIONS_MSG

    lines = [
        f"Owner predictions — {result.get('date')} ({result.get('timezone')}) — scope={result.get('scope')}",
        "-" * 100,
        f"{'ID':<10} {'Kickoff':<20} {'Match':<32} {'Pick':<6} {'Score':<8} {'Conf':<6} {'Eval':<10} {'Actual':<8}",
    ]
    for p in result.get("predictions") or []:
        match = f"{p.get('home_team', '?')} vs {p.get('away_team', '?')}"[:31]
        lines.append(
            f"{str(p.get('fixture_id', '')):<10} "
            f"{str(p.get('kickoff_utc', ''))[:19]:<20} "
            f"{match:<32} "
            f"{str(p.get('main_pick') or '-'):<6} "
            f"{str(p.get('predicted_scoreline') or '-'):<8} "
            f"{str(p.get('confidence') or '-'):<6} "
            f"{str(p.get('evaluation_outcome') or '-'):<10} "
            f"{str(p.get('actual_result') or '-'):<8}"
        )
    return "\n".join(lines)


def format_predictions_markdown(result: dict[str, Any]) -> str:
    if result.get("status") == "error":
        return f"**Error:** {result.get('error')}"
    if result.get("status") == "empty":
        return f"**{NO_PREDICTIONS_MSG}**"

    lines = [
        f"# Owner predictions — {result.get('date')}",
        "",
        f"- Timezone: `{result.get('timezone')}`",
        f"- Scope: `{result.get('scope')}`",
        f"- Count: **{result.get('count')}**",
        "",
        "| Fixture | Match | Kickoff | Pick | Score | Conf | Eval | Actual |",
        "| ------- | ----- | ------- | ---- | ----- | ---- | ---- | ------ |",
    ]
    for p in result.get("predictions") or []:
        match = f"{p.get('home_team', '?')} vs {p.get('away_team', '?')}"
        lines.append(
            f"| {p.get('fixture_id')} | {match} | {p.get('kickoff_utc', '')} "
            f"| {p.get('main_pick') or '—'} | {p.get('predicted_scoreline') or '—'} "
            f"| {p.get('confidence') or '—'} | {p.get('evaluation_outcome') or '—'} "
            f"| {p.get('actual_result') or '—'} |"
        )
    return "\n".join(lines)


def format_predictions_output(result: dict[str, Any], fmt: OutputFormat) -> str:
    if fmt == "json":
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)
    if fmt == "markdown":
        return format_predictions_markdown(result)
    return format_predictions_table(result)


def sanitize_for_output(text: str) -> str:
    return _redact_secrets(text)
