"""Unified Hybrid Prediction Engine — Phase 61 orchestrator."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.predops.constants import ALL_MARKET_IDS
from worldcup_predictor.unified_hybrid.confidence import confidence_to_tier
from worldcup_predictor.unified_hybrid.decision_layer import (
    build_combo_candidates,
    fuse_market,
    select_best_tip,
)
from worldcup_predictor.unified_hybrid.feature_store import UnifiedFixtureFeatureStore
from worldcup_predictor.unified_hybrid.models import UnifiedPredictionOutput
from worldcup_predictor.unified_hybrid.specialists import (
    ClassicSpecialist,
    EGIESpecialist,
    LineupInjurySpecialist,
    OddsMarketSpecialist,
)

HYBRID_MARKET_IDS = tuple(
    m for m in ALL_MARKET_IDS
    if m in {
        "1x2", "btts", "over_under_2_5", "double_chance", "correct_score", "ht_result",
        "first_goal_team", "first_goal_time_range", "estimated_first_goal_minute",
        "anytime_goalscorer", "first_goalscorer",
    }
)


class UnifiedHybridPredictionEngine:
    """
    Orchestrates Classic, EGIE, and provider specialists into one unified output.
    Does NOT modify ScoringEngine, WDE, or EliteGoalTimingEngine internals.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.features = UnifiedFixtureFeatureStore(self.settings)
        self.classic = ClassicSpecialist(self.settings)
        self.egie = EGIESpecialist(self.settings)

    def is_enabled(self) -> bool:
        return bool(self.settings.unified_engine_enabled)

    def admin_preview_allowed(self) -> bool:
        return bool(self.settings.unified_engine_admin_preview)

    def public_allowed(self) -> bool:
        return bool(self.settings.unified_engine_public and self.settings.unified_engine_enabled)

    def compare_mode(self) -> bool:
        return bool(self.settings.unified_engine_compare_mode)

    def predict(
        self,
        fixture_id: int,
        *,
        competition_key: str | None = None,
        include_compare: bool | None = None,
    ) -> UnifiedPredictionOutput:
        feat = self.features.build(
            int(fixture_id),
            competition_key=competition_key or "",
            home_team="",
            away_team="",
        )
        comp = competition_key or feat.get("competition_key")
        classic_payload = feat.get("stored_classic_payload") or {}

        classic = self.classic.load(int(fixture_id), payload=classic_payload or None)
        egie = self.egie.load(int(fixture_id), classic_payload=classic_payload)
        odds = OddsMarketSpecialist.summarize(feat.get("provider_fields") or {})
        _ = LineupInjurySpecialist.summarize(feat)

        markets: dict[str, Any] = {}
        for market_id in HYBRID_MARKET_IDS:
            markets[market_id] = fuse_market(
                market_id,
                classic=classic,
                egie=egie,
                odds=odds,
                features=feat,
            )

        best = select_best_tip(markets)
        combos = build_combo_candidates(markets)
        overall_conf = best.confidence if best else None
        overall_tier = confidence_to_tier(overall_conf)

        compare = None
        if include_compare if include_compare is not None else self.compare_mode():
            compare = {
                "classic_status": classic.get("status"),
                "egie_status": egie.get("status"),
                "classic_engine": classic.get("engine_version"),
                "egie_engine": egie.get("engine_version"),
                "classic_best": _extract_classic_best(classic),
                "egie_best": _extract_egie_best(egie),
            }

        return UnifiedPredictionOutput(
            fixture_id=int(fixture_id),
            competition_key=comp,
            home_team=feat.get("home_team") or "",
            away_team=feat.get("away_team") or "",
            kickoff_utc=feat.get("kickoff_utc"),
            fixture_status=feat.get("fixture_status"),
            markets=markets,
            best_tip=best,
            combo_candidates=combos,
            overall_confidence=overall_conf,
            overall_tier=overall_tier,
            data_quality_score=feat.get("data_quality_score"),
            feature_freshness=feat.get("feature_freshness") or {},
            missing_data_warnings=feat.get("missing_data_warnings") or [],
            component_contributions={
                "classic": classic.get("status"),
                "egie": egie.get("status"),
                "odds": odds.get("status"),
                "provider_coverage": feat.get("provider_coverage"),
            },
            engine_versions={
                "classic": str(classic.get("engine_version") or "classic"),
                "egie": str(egie.get("engine_version") or "egie"),
                "unified": "61-v1",
            },
            compare_mode=compare,
        )


def _extract_classic_best(classic: dict[str, Any]) -> dict[str, Any] | None:
    payload = classic.get("payload") or {}
    pick = payload.get("best_available_pick") or payload.get("user_visible_pick") or payload.get("prediction")
    if isinstance(pick, dict):
        return {"selection": pick.get("pick") or pick.get("selection"), "confidence": pick.get("confidence")}
    if pick:
        return {"selection": str(pick), "confidence": payload.get("confidence")}
    return None


def _extract_egie_best(egie: dict[str, Any]) -> dict[str, Any] | None:
    snap = egie.get("snapshot") or {}
    if snap.get("first_goal_team"):
        return {"selection": snap.get("first_goal_team"), "confidence": snap.get("confidence")}
    if snap.get("first_goal_time_range"):
        return {"selection": snap.get("first_goal_time_range"), "confidence": snap.get("confidence")}
    return None
