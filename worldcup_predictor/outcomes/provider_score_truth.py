"""Parse provider fixture payloads into explicit FT / AET / PEN stage truth."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.outcomes.outcome_persistence import normalize_match_outcome_type


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class ResultStageTruth:
    """Explicit stage-separated scores from a finished provider fixture item."""

    regulation_home: int | None
    regulation_away: int | None
    extra_time_home: int | None
    extra_time_away: int | None
    penalties_home: int | None
    penalties_away: int | None
    final_stage: str
    qualified_team: str | None
    legacy_home: int | None
    legacy_away: int | None
    source: str = "api-football"

    @property
    def regulation_score(self) -> str | None:
        if self.regulation_home is None or self.regulation_away is None:
            return None
        return f"{self.regulation_home}-{self.regulation_away}"

    @property
    def extra_time_score(self) -> str | None:
        if self.extra_time_home is None or self.extra_time_away is None:
            return None
        return f"{self.extra_time_home}-{self.extra_time_away}"

    @property
    def penalties_score(self) -> str | None:
        if self.penalties_home is None or self.penalties_away is None:
            return None
        return f"{self.penalties_home}-{self.penalties_away}"


def parse_provider_fixture_item(item: dict[str, Any], *, source: str = "api-football") -> ResultStageTruth | None:
    """Extract regulation / AET / PEN truth from one API-Football fixtures response item."""
    if not isinstance(item, dict):
        return None
    fixture_meta = item.get("fixture") or {}
    status_obj = fixture_meta.get("status") or {}
    status_short = str(status_obj.get("short") or "NS").upper()
    teams = item.get("teams") or {}
    home_team = str((teams.get("home") or {}).get("name") or "")
    away_team = str((teams.get("away") or {}).get("name") or "")

    goals = item.get("goals") or {}
    score = item.get("score") or {}
    fulltime = score.get("fulltime") or {}
    penalty = score.get("penalty") or {}

    legacy_home = _int_or_none(goals.get("home"))
    legacy_away = _int_or_none(goals.get("away"))
    reg_home = _int_or_none(fulltime.get("home"))
    reg_away = _int_or_none(fulltime.get("away"))

    if reg_home is None or reg_away is None:
        if status_short == "FT" and legacy_home is not None and legacy_away is not None:
            reg_home, reg_away = legacy_home, legacy_away
        else:
            return None

    final_stage = normalize_match_outcome_type(status_short)
    if final_stage not in {"FT", "AET", "PEN"}:
        final_stage = status_short if status_short in {"FT", "AET", "PEN"} else "FT"

    et_home = et_away = None
    if final_stage == "AET" and legacy_home is not None and legacy_away is not None:
        et_home, et_away = legacy_home, legacy_away

    pen_home = _int_or_none(penalty.get("home"))
    pen_away = _int_or_none(penalty.get("away"))

    qualified: str | None = None
    if final_stage == "PEN" and pen_home is not None and pen_away is not None:
        if pen_home > pen_away:
            qualified = home_team
        elif pen_away > pen_home:
            qualified = away_team
    elif final_stage == "AET" and legacy_home is not None and legacy_away is not None:
        if legacy_home > legacy_away:
            qualified = home_team
        elif legacy_away > legacy_home:
            qualified = away_team
    elif reg_home != reg_away:
        qualified = home_team if reg_home > reg_away else away_team

    return ResultStageTruth(
        regulation_home=reg_home,
        regulation_away=reg_away,
        extra_time_home=et_home,
        extra_time_away=et_away,
        penalties_home=pen_home,
        penalties_away=pen_away,
        final_stage=final_stage,
        qualified_team=qualified,
        legacy_home=legacy_home,
        legacy_away=legacy_away,
        source=source,
    )


def truth_from_result_row(result_row: dict[str, Any] | None) -> ResultStageTruth | None:
    """Reconstruct stage truth from a fixture_results row (after migration/backfill)."""
    if not result_row:
        return None
    reg_h = result_row.get("regulation_home_goals")
    reg_a = result_row.get("regulation_away_goals")
    if reg_h is None or reg_a is None:
        mot = str(result_row.get("match_outcome_type") or "FT").upper()
        h = result_row.get("home_goals")
        a = result_row.get("away_goals")
        if h is None or a is None:
            return None
        if mot in {"FT", "PEN"}:
            reg_h, reg_a = int(h), int(a)
        else:
            return None
    pen_h = result_row.get("penalties_home_goals")
    pen_a = result_row.get("penalties_away_goals")
    if pen_h is None and result_row.get("penalty_score") and "-" in str(result_row["penalty_score"]):
        try:
            pen_h, pen_a = [int(x.strip()) for x in str(result_row["penalty_score"]).split("-", 1)]
        except ValueError:
            pen_h = pen_a = None
    return ResultStageTruth(
        regulation_home=int(reg_h),
        regulation_away=int(reg_a),
        extra_time_home=result_row.get("extra_time_home_goals"),
        extra_time_away=result_row.get("extra_time_away_goals"),
        penalties_home=pen_h,
        penalties_away=pen_a,
        final_stage=str(result_row.get("final_stage") or result_row.get("match_outcome_type") or "FT").upper(),
        qualified_team=result_row.get("qualified_team"),
        legacy_home=result_row.get("home_goals"),
        legacy_away=result_row.get("away_goals"),
        source=str(result_row.get("outcome_source") or result_row.get("source") or "db"),
    )
