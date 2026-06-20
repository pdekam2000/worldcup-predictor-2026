"""Shadow scoreline path — parallel to production, never mutates published prediction."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from worldcup_predictor.domain.prediction import MatchPrediction, ScorelinePrediction
from worldcup_predictor.prediction.consistency_engine import harmonize_prediction
from worldcup_predictor.prediction.lambda_bridge.bridge import SpecialistLambdaBridge
from worldcup_predictor.prediction.lambda_bridge.models import LambdaBridgeMode
from worldcup_predictor.prediction.lambda_bridge.shadow_store import ShadowRecord, ShadowStore
from worldcup_predictor.prediction.scoreline_engine import (
    _expected_goals_from_report,
    generate_scoreline_candidates,
    primary_scoreline,
)

if TYPE_CHECKING:
    from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
    from worldcup_predictor.domain.specialist import MatchSpecialistReport

logger = logging.getLogger(__name__)


def _conflict_change(published_conflict: bool, shadow_conflict: bool) -> str:
    if published_conflict and not shadow_conflict:
        return "improved"
    if not published_conflict and shadow_conflict:
        return "worsened"
    return "unchanged"


def compute_shadow_scoreline(
    report: MatchIntelligenceReport,
    *,
    lambda_home: float,
    lambda_away: float,
) -> tuple[str, int, int]:
    candidates = generate_scoreline_candidates(
        report,
        home_lambda=lambda_home,
        away_lambda=lambda_away,
    )
    h, a = primary_scoreline(candidates)
    return f"{h}-{a}", h, a


def build_shadow_prediction(
    production: MatchPrediction,
    *,
    home_name: str,
    away_name: str,
    shadow_h: int,
    shadow_a: int,
) -> MatchPrediction:
    shadow = replace(
        production,
        scoreline=ScorelinePrediction(home_goals=float(shadow_h), away_goals=float(shadow_a)),
    )
    return harmonize_prediction(shadow, home_team=home_name, away_team=away_name)


def maybe_record_shadow(
    *,
    production: MatchPrediction,
    report: MatchIntelligenceReport,
    specialist_report: MatchSpecialistReport | None,
    home_name: str,
    away_name: str,
    wde_selection: str,
    mode: LambdaBridgeMode,
    shadow_path: str | None = None,
    config_version: str | None = None,
) -> None:
    """Run shadow bridge in parallel; never changes production prediction."""
    if mode not in ("shadow", "limited", "full"):
        return

    try:
        lambda_base_h, lambda_base_a = _expected_goals_from_report(report)
        bridge = SpecialistLambdaBridge()
        bridge_result = bridge.compute(
            report=report,
            specialist_report=specialist_report,
            lambda_base_home=lambda_base_h,
            lambda_base_away=lambda_base_a,
            mode="full" if mode == "shadow" else mode,
        )

        prod_scoreline = "—"
        if production.scoreline:
            prod_scoreline = f"{int(round(production.scoreline.home_goals))}-{int(round(production.scoreline.away_goals))}"

        shadow_scoreline_str, sh, sa = compute_shadow_scoreline(
            report,
            lambda_home=bridge_result.lambda_adjusted_home,
            lambda_away=bridge_result.lambda_adjusted_away,
        )
        shadow_pred = build_shadow_prediction(
            production,
            home_name=home_name,
            away_name=away_name,
            shadow_h=sh,
            shadow_a=sa,
        )

        pub_sel = production.one_x_two.selection
        shadow_sel = shadow_pred.one_x_two.selection
        pub_conflict = wde_selection != pub_sel
        shadow_conflict = wde_selection != shadow_sel

        record = ShadowRecord(
            fixture_id=production.fixture_id,
            match_name=production.match_name,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            mode=mode,
            config_version=config_version or bridge_result.config_version,
            production_prediction=pub_sel,
            shadow_prediction=shadow_sel,
            production_lambda_home=round(lambda_base_h, 4),
            production_lambda_away=round(lambda_base_a, 4),
            shadow_lambda_home=round(bridge_result.lambda_adjusted_home, 4),
            shadow_lambda_away=round(bridge_result.lambda_adjusted_away, 4),
            production_scoreline=prod_scoreline,
            shadow_scoreline=shadow_scoreline_str,
            wde_selection=wde_selection,
            bridge_contributors=[c.to_dict() for c in bridge_result.contributions],
            conflict_status={
                "production_conflict": pub_conflict,
                "shadow_conflict": shadow_conflict,
                "conflict_change": _conflict_change(pub_conflict, shadow_conflict),
            },
            global_cap_applied=bridge_result.global_cap_applied,
            data_quality_scale=bridge_result.data_quality_scale,
            data_quality_pct=bridge_result.data_quality_pct,
        )

        store = ShadowStore(shadow_path) if shadow_path else ShadowStore()
        store.append(record)

        if pub_sel != production.one_x_two.selection:
            logger.error(
                "lambda_bridge shadow invariant violated fixture=%s",
                production.fixture_id,
            )
    except Exception:
        logger.exception(
            "lambda_bridge shadow recording failed fixture=%s (fail-closed)",
            production.fixture_id,
        )
