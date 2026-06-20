"""Shadow scoreline path for odds-primary engine — never mutates production."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.prediction.odds_primary.engine import OddsPrimaryScorelineEngine
from worldcup_predictor.prediction.odds_primary.models import OddsPrimaryMode
from worldcup_predictor.prediction.odds_primary.shadow_store import OddsPrimaryShadowRecord, OddsPrimaryShadowStore
from worldcup_predictor.prediction.scoreline_engine import (
    _expected_goals_from_report,
    generate_scoreline_candidates,
    primary_scoreline,
)

logger = logging.getLogger(__name__)


def _result_1x2(h: int, a: int) -> str:
    if h > a:
        return "home_win"
    if a > h:
        return "away_win"
    return "draw"


def shadow_scoreline_from_lambdas(
    report: MatchIntelligenceReport,
    *,
    lambda_home: float,
    lambda_away: float,
) -> tuple[str, str]:
    candidates = generate_scoreline_candidates(
        report,
        home_lambda=lambda_home,
        away_lambda=lambda_away,
    )
    h, a = primary_scoreline(candidates)
    return f"{h}-{a}", _result_1x2(h, a)


def maybe_record_odds_primary_shadow(
    *,
    production: MatchPrediction,
    report: MatchIntelligenceReport,
    actual_result: str | None,
    mode: OddsPrimaryMode,
    shadow_path: str | None = None,
    config_version: str | None = None,
) -> None:
    if mode != "shadow":
        return
    try:
        prod_lh, prod_la = _expected_goals_from_report(report)
        engine = OddsPrimaryScorelineEngine(config_version=config_version or "16-v1")
        shadow_result = engine.compute(report)
        prod_sl, _ = shadow_scoreline_from_lambdas(report, lambda_home=prod_lh, lambda_away=prod_la)
        shadow_sl, shadow_sel = shadow_scoreline_from_lambdas(
            report,
            lambda_home=shadow_result.lambda_home,
            lambda_away=shadow_result.lambda_away,
        )
        prod_sel = production.one_x_two.selection
        record = OddsPrimaryShadowRecord(
            fixture_id=production.fixture_id,
            match_name=production.match_name,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            config_version=engine.config_version,
            production_prediction=prod_sel,
            shadow_prediction=shadow_sel,
            production_lambda_home=round(prod_lh, 4),
            production_lambda_away=round(prod_la, 4),
            shadow_lambda_home=shadow_result.lambda_home,
            shadow_lambda_away=shadow_result.lambda_away,
            production_scoreline=prod_sl,
            shadow_scoreline=shadow_sl,
            actual_result=actual_result,
            production_correct=prod_sel == actual_result if actual_result else None,
            shadow_correct=shadow_sel == actual_result if actual_result else None,
            lambda_source=shadow_result.lambda_source,
            odds_available=shadow_result.odds_available,
            shadow_meta=shadow_result.to_dict(),
        )
        store = OddsPrimaryShadowStore(shadow_path) if shadow_path else OddsPrimaryShadowStore()
        store.append(record)
    except Exception:
        logger.exception(
            "odds_primary shadow failed fixture=%s (fail-closed)",
            production.fixture_id,
        )
