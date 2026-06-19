"""Rule A live forward validation recorder (Phase 21A-LIVE)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from worldcup_predictor.prediction.rule_a_gate.live_validation_store import (
    DEFAULT_MANIFEST_PATH,
    LiveValidationRecord,
    LiveValidationStore,
)
from worldcup_predictor.prediction.rule_a_gate.shadow_runner import (
    _scoreline_to_1x2,
    compute_rule_a_prediction,
)

if TYPE_CHECKING:
    from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
    from worldcup_predictor.domain.prediction import MatchPrediction

logger = logging.getLogger(__name__)


def maybe_record_rule_a_live(
    *,
    production: MatchPrediction,
    report: MatchIntelligenceReport,
    wde_selection: str,
    scoreline_home: int,
    scoreline_away: int,
    enabled: bool,
    live_path: str | None = None,
    manifest_path: str | None = None,
) -> None:
    """Append forward-only live validation record; production unchanged."""
    if not enabled:
        return

    try:
        odds = report.odds
        odds_available = bool(odds and odds.available and odds.bookmakers)
        dq = (report.data_quality.score * 100) if report.data_quality else 40.0
        scoreline_pred = _scoreline_to_1x2(scoreline_home, scoreline_away)
        rule_a_pred, _ = compute_rule_a_prediction(
            wde_prediction=wde_selection,
            scoreline_prediction=scoreline_pred,
            odds_available=odds_available,
        )

        store = LiveValidationStore(
            path=live_path or LiveValidationStore().path,
            manifest_path=manifest_path or DEFAULT_MANIFEST_PATH,
        )
        store.ensure_manifest()
        ts = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        store.append(
            LiveValidationRecord(
                fixture_id=production.fixture_id,
                prediction_timestamp=ts,
                production_prediction=production.one_x_two.selection,
                wde_prediction=wde_selection,
                scoreline_prediction=scoreline_pred,
                rule_a_prediction=rule_a_pred,
                odds_available=odds_available,
                data_quality_pct=round(dq, 1),
                actual_result=None,
                settled=False,
                match_name=production.match_name,
            )
        )
    except Exception:
        logger.exception(
            "rule_a live validation recording failed fixture=%s (fail-closed)",
            production.fixture_id,
        )
