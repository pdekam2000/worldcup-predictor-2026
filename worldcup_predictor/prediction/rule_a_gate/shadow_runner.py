"""Rule A shadow recorder — parallel path; production prediction unchanged."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from worldcup_predictor.prediction.rule_a_gate.models import RuleAGateMode
from worldcup_predictor.prediction.rule_a_gate.shadow_store import RuleAShadowRecord, RuleAShadowStore

if TYPE_CHECKING:
    from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
    from worldcup_predictor.domain.prediction import MatchPrediction

logger = logging.getLogger(__name__)


def _scoreline_to_1x2(home: int, away: int) -> str:
    if home > away:
        return "home_win"
    if home < away:
        return "away_win"
    return "draw"


def compute_rule_a_prediction(
    *,
    wde_prediction: str,
    scoreline_prediction: str,
    odds_available: bool,
) -> tuple[str, str]:
    if odds_available:
        return scoreline_prediction, "scoreline"
    return wde_prediction, "wde"


def maybe_record_rule_a_shadow(
    *,
    production: MatchPrediction,
    report: MatchIntelligenceReport,
    wde_selection: str,
    scoreline_home: int,
    scoreline_away: int,
    mode: RuleAGateMode,
    shadow_path: str | None = None,
) -> None:
    """Record Rule A shadow pick; never mutates production."""
    if mode != "shadow":
        return

    try:
        odds = report.odds
        odds_available = bool(odds and odds.available and odds.bookmakers)
        dq = (report.data_quality.score * 100) if report.data_quality else 40.0

        scoreline_pred = _scoreline_to_1x2(scoreline_home, scoreline_away)
        rule_a_pred, source = compute_rule_a_prediction(
            wde_prediction=wde_selection,
            scoreline_prediction=scoreline_pred,
            odds_available=odds_available,
        )

        prod_sl = "—"
        if production.scoreline:
            prod_sl = (
                f"{int(round(production.scoreline.home_goals))}-"
                f"{int(round(production.scoreline.away_goals))}"
            )

        record = RuleAShadowRecord(
            fixture_id=production.fixture_id,
            match_name=production.match_name,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            production_prediction=production.one_x_two.selection,
            wde_prediction=wde_selection,
            scoreline_prediction=scoreline_pred,
            rule_a_prediction=rule_a_pred,
            odds_available=odds_available,
            data_quality_pct=round(dq, 1),
            production_scoreline=prod_sl,
            scoreline_str=f"{scoreline_home}-{scoreline_away}",
            rule_a_source=source,
        )

        store = RuleAShadowStore(shadow_path) if shadow_path else RuleAShadowStore()
        store.append(record)
    except Exception:
        logger.exception(
            "rule_a shadow recording failed fixture=%s (fail-closed)",
            production.fixture_id,
        )
