"""Feature extraction for ECSE shadow re-rank — read-only."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

PHASE = "ECSE-RERANK-1"
KNOCKOUT_STALE_HOURS = 6.0
NORMAL_STALE_HOURS = 24.0

BTTS_BOOST_LINES = frozenset(
    {"1-1", "2-1", "1-2", "2-2", "3-1", "1-3", "3-2", "2-3"}
)
OVER_BOOST_LINES = frozenset(
    {"2-1", "1-2", "3-0", "0-3", "3-1", "1-3", "2-2", "3-2", "2-3", "4-0", "0-4", "3-3"}
)
CLEAN_SHEET_LINES = frozenset({"1-0", "2-0", "3-0", "4-0", "0-1", "0-2", "0-3", "0-4"})
FAVORITE_MARGIN_BTTS = frozenset({"2-1", "3-1", "3-2", "4-1", "4-2"})


def parse_scoreline(line: str) -> tuple[int, int] | None:
    if not line or "-" not in str(line):
        return None
    try:
        h, a = str(line).replace(":", "-").split("-", 1)
        return int(h.strip()), int(a.strip())
    except (TypeError, ValueError):
        return None


def total_goals(line: str) -> int | None:
    parsed = parse_scoreline(line)
    return parsed[0] + parsed[1] if parsed else None


def is_clean_sheet(line: str) -> bool:
    parsed = parse_scoreline(line)
    if not parsed:
        return False
    h, a = parsed
    return h == 0 or a == 0


def is_btts(line: str) -> bool:
    parsed = parse_scoreline(line)
    if not parsed:
        return False
    h, a = parsed
    return h > 0 and a > 0


def winner_side(line: str) -> str | None:
    parsed = parse_scoreline(line)
    if not parsed:
        return None
    h, a = parsed
    if h > a:
        return "home_win"
    if h < a:
        return "away_win"
    return "draw"


def parse_json_list(raw: Any) -> list[Any]:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def parse_top10(raw: Any) -> list[dict[str, Any]]:
    items = parse_json_list(raw)
    out: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        if isinstance(item, dict):
            line = item.get("scoreline") or item.get("label")
            prob = float(item.get("probability") or 0)
            rank = int(item.get("rank") or i + 1)
        else:
            line = str(item)
            prob = 0.0
            rank = i + 1
        if line:
            parsed = parse_scoreline(line)
            out.append(
                {
                    "scoreline": str(line),
                    "probability": prob,
                    "rank": rank,
                    "home_goals": parsed[0] if parsed else None,
                    "away_goals": parsed[1] if parsed else None,
                }
            )
    return out


def extract_wde_markets(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    one_x_two = payload.get("one_x_two") or {}
    detailed = payload.get("detailed_markets") or {}
    if not one_x_two and detailed.get("match_winner"):
        one_x_two = detailed["match_winner"]
    over_under = payload.get("over_under") or detailed.get("over_under_25") or {}
    btts = (payload.get("extended_markets") or {}).get("btts") or detailed.get("btts") or {}

    btts_sel = btts.get("selection")
    if btts_sel:
        btts_sel = str(btts_sel).lower().replace("btts_", "")
    else:
        yes = float(btts.get("yes") or btts.get("probability") or 0)
        btts_sel = "yes" if yes >= 0.5 else "no"

    conf = payload.get("confidence_score") or payload.get("confidence")
    try:
        conf_f = float(conf) if conf is not None else None
        if conf_f is not None and conf_f <= 1:
            conf_f *= 100
    except (TypeError, ValueError):
        conf_f = None

    return {
        "pick_1x2": one_x_two.get("selection"),
        "pick_ou25": over_under.get("selection"),
        "pick_btts": btts_sel,
        "confidence_score": conf_f,
        "prob_home": one_x_two.get("home") or one_x_two.get("probability"),
        "prob_draw": one_x_two.get("draw"),
        "prob_away": one_x_two.get("away"),
    }


def is_knockout_fixture(fixture_row: dict[str, Any]) -> bool:
    stage = str(fixture_row.get("round_name") or fixture_row.get("stage") or "").lower()
    status = str(fixture_row.get("status") or "").upper()
    if any(k in stage for k in ("round of", "knockout", "quarter", "semi", "final")):
        return True
    return status in {"AET", "PEN"}


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def odds_freshness_meta(
    *,
    odds_snapshot_at: str | None,
    prediction_generated_at: str | None,
    knockout: bool,
    odds_source: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper — delegates to central freshness policy."""
    from worldcup_predictor.odds.freshness_policy import classify_odds_freshness

    cls = classify_odds_freshness(
        odds_snapshot_at=odds_snapshot_at,
        reference_at=prediction_generated_at,
        knockout=knockout,
        odds_source=odds_source,
        has_odds=bool(odds_snapshot_at),
    )
    out = cls.to_dict()
    out["prediction_generated_at"] = prediction_generated_at
    return out


def result_context(fixture_row: dict[str, Any], result_row: dict[str, Any] | None) -> dict[str, Any]:
    status = str(fixture_row.get("status") or "").upper()
    ended_aet = status == "AET"
    ended_pen = status == "PEN"
    h = a = None
    score_90 = None
    if result_row:
        h = result_row.get("home_goals")
        a = result_row.get("away_goals")
        if h is not None and a is not None:
            score_90 = f"{int(h)}-{int(a)}"
    return {
        "fixture_status": status,
        "ended_in_extra_time": ended_aet,
        "ended_on_penalties": ended_pen,
        "result_90min": score_90,
        "result_after_extra_time": score_90 if ended_aet else None,
        "penalty_score": (result_row or {}).get("penalty_score"),
        "match_outcome_type": (result_row or {}).get("match_outcome_type"),
        "eval_use_90min_only": ended_aet or ended_pen,
    }
