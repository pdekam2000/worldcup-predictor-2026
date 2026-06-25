"""Hybrid per-market confidence engine (Design C — shadow only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.egie.confidence.config import HYBRID_CONFIDENCE_MODEL_VERSION, TEAM_ABSTAIN_GAP
from worldcup_predictor.egie.confidence.metrics import (
    clamp01,
    hazard_concentration,
    normalized_entropy,
    probability_margin,
)
from worldcup_predictor.egie.confidence.models import (
    HybridConfidenceResult,
    HybridConfidenceScores,
    HybridConfidenceTiers,
)
from worldcup_predictor.egie.confidence.reliability import ReliabilityPriorStore
from worldcup_predictor.egie.confidence.tier_mapper import (
    MarketTierCalibrator,
    TierCalibration,
    build_ui,
    map_tiers,
)
from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES


def _team_conditional_gap(team_probs: dict[str, float]) -> tuple[float, float]:
    p_home = float(team_probs.get("home_first_goal_probability") or 0.0)
    p_away = float(team_probs.get("away_first_goal_probability") or 0.0)
    directional = p_home + p_away
    if directional <= 0:
        return 0.0, 0.0
    home_cond = p_home / directional
    away_cond = p_away / directional
    gap = abs(home_cond - away_cond)
    abstention_dist = max(0.0, gap - TEAM_ABSTAIN_GAP) / max(1e-9, 1.0 - TEAM_ABSTAIN_GAP)
    return round(gap, 4), round(abstention_dist, 4)


def _profile_strength(range_probs: dict[str, float]) -> float:
    early = float(range_probs.get("0-15") or 0.0) + float(range_probs.get("16-30") or 0.0)
    late = float(range_probs.get("61-75") or 0.0) + float(range_probs.get("76-90+") or 0.0)
    return round(abs(early - late), 4)


def _data_completeness(features: dict[str, Any], data_quality: float) -> float:
    hs = features.get("history_samples") or {}
    depth = int(hs.get("home_matches") or 0) + int(hs.get("away_matches") or 0)
    depth_norm = min(1.0, depth / 40.0)
    manifest = features.get("provider_manifest") or {}
    coverage = sum(1 for v in manifest.values() if v) / max(len(manifest), 1) if manifest else 0.5
    return round(0.6 * float(data_quality) + 0.25 * depth_norm + 0.15 * coverage, 4)


class HybridConfidenceEngine:
    """Compute conf_team, conf_range, conf_minute — replaces single scalar in shadow mode."""

    def score(
        self,
        *,
        fixture_id: int,
        competition_key: str,
        features: dict[str, Any],
        baseline: dict[str, Any],
        survival: dict[str, Any],
        data_quality_score: float,
        reliability: ReliabilityPriorStore,
        tier_calibration: TierCalibration,
        home_team: str = "",
        away_team: str = "",
        team_calibrator: MarketTierCalibrator | None = None,
        range_calibrator: MarketTierCalibrator | None = None,
        minute_calibrator: MarketTierCalibrator | None = None,
    ) -> HybridConfidenceResult:
        range_probs = survival.get("range_probabilities") or baseline.get("match_first_goal_range_probs") or {}
        team_probs = survival.get("team_probabilities") or {}
        hazard = survival.get("hazard_curve") or {}
        hazard_by = hazard.get("hazard_by_bucket") or {}

        team_gap, abstention_dist = _team_conditional_gap(team_probs)
        if team_gap == 0.0:
            home_rate = float(survival.get("home_goal_rate") or 0.33)
            away_rate = float(survival.get("away_goal_rate") or 0.33)
            total = max(1e-9, home_rate + away_rate)
            team_gap = round(abs(home_rate / total - away_rate / total), 4)
            abstention_dist = round(
                max(0.0, team_gap - TEAM_ABSTAIN_GAP) / max(1e-9, 1.0 - TEAM_ABSTAIN_GAP),
                4,
            )

        surv_range_margin = probability_margin(range_probs, keys=list(GOAL_TIMING_MINUTE_RANGES))
        base_range_margin = probability_margin(
            baseline.get("match_first_goal_range_probs") or {},
            keys=list(GOAL_TIMING_MINUTE_RANGES),
        )
        range_margin = max(surv_range_margin, base_range_margin)

        haz_conc = hazard_concentration(hazard_by) if hazard_by else surv_range_margin
        entropy_inv = round(1.0 - normalized_entropy(range_probs, keys=list(GOAL_TIMING_MINUTE_RANGES)), 4)
        profile = _profile_strength(range_probs)
        completeness = _data_completeness(features, data_quality_score)

        hist_team = reliability.team_reliability(home_team, away_team)
        hist_range = reliability.range_reliability(competition_key)

        predicted_team = str(baseline.get("first_goal_team") or survival.get("first_goal_team") or "none")
        none_penalty = 0.55 if predicted_team == "none" else 1.0

        conf_team = clamp01(
            (
                0.18 * completeness
                + 0.32 * min(1.0, team_gap / 0.22)
                + 0.22 * abstention_dist
                + 0.14 * profile
                + 0.14 * hist_team
            )
            * none_penalty
        )

        conf_range = clamp01(
            0.42 * range_margin
            + 0.28 * haz_conc
            + 0.18 * entropy_inv
            + 0.12 * hist_range
        )

        peak_hazard = float(hazard.get("peak_hazard") or haz_conc)
        cluster_density = max(float(range_probs.get(k) or 0.0) for k in GOAL_TIMING_MINUTE_RANGES)
        conf_minute = clamp01(
            (0.38 * min(1.0, peak_hazard * 4.0) + 0.34 * cluster_density + 0.28 * entropy_inv)
            * 0.88
        )

        scores = HybridConfidenceScores(
            conf_team=conf_team,
            conf_range=conf_range,
            conf_minute=conf_minute,
            data_completeness=completeness,
            team_probability_gap=team_gap,
            abstention_distance=abstention_dist,
            survival_range_margin=surv_range_margin,
            hazard_concentration=haz_conc,
            timing_entropy_inverse=entropy_inv,
            historical_team_reliability=hist_team,
            historical_range_reliability=hist_range,
        )

        team_tier, range_tier, minute_tier, display_tier = map_tiers(
            conf_team=conf_team,
            conf_range=conf_range,
            conf_minute=conf_minute,
            calibration=tier_calibration,
            team_calibrator=team_calibrator,
            range_calibrator=range_calibrator,
            minute_calibrator=minute_calibrator,
        )
        tiers = HybridConfidenceTiers(
            team_tier=team_tier,
            range_tier=range_tier,
            minute_tier=minute_tier,
            display_tier=display_tier,
        )
        ui = build_ui(
            team_tier=team_tier,
            range_tier=range_tier,
            minute_tier=minute_tier,
            predicted_team_none=predicted_team == "none",
        )

        legacy = baseline.get("confidence_score")
        if legacy is None:
            legacy = survival.get("confidence_score")

        return HybridConfidenceResult(
            fixture_id=fixture_id,
            competition_key=competition_key,
            model_version=HYBRID_CONFIDENCE_MODEL_VERSION,
            shadow_mode=True,
            scores=scores,
            tiers=tiers,
            ui=ui,
            legacy_confidence_score=float(legacy) if legacy is not None else None,
            components={
                "base_range_margin": base_range_margin,
                "profile_strength": profile,
                "peak_hazard": round(peak_hazard, 4),
                "cluster_density": round(cluster_density, 4),
            },
        )
