"""Betting Day Feature Stability & OOD Forensic Audit — research-only."""

PHASE_NAME = "BETTING_DAY_FEATURE_STABILITY_AND_OOD_FORENSIC_AUDIT"
STATUS_COMPLETE = "BETTING_DAY_FEATURE_STABILITY_AND_OOD_FORENSIC_COMPLETE"
BASELINE_COMMIT = "f8187ac"
LOCKED_METHOD = "cosine"
LOCKED_K = 10
LOCKED_REGIMES = 3
REPORTED_OOD_DAYS = 75
REPORTED_FEATURE_COUNT = 72

FEATURE_GROUPS = {
    "league": [
        "n_countries",
        "n_leagues",
        "league_concentration",
        "max_league_share",
        "avg_fixtures_per_league",
        "reserve_youth_women_friendly_flag",
        "avg_competition_tier",
        "league_correlation_score",
        "rolling_league_reliability",
    ],
    "market": [
        "avg_favorite_odds",
        "median_favorite_odds",
        "avg_draw_odds",
        "pct_balanced_market",
        "pct_one_sided_market",
        "favorite_strength_bucket",
        "expected_total_bucket",
        "pct_btts_yes",
        "pct_over_direction",
        "bookmaker_completeness",
        "real_market_completeness",
        "avg_market_families",
        "market_family_entropy",
        "market_correlation_score",
        "rolling_market_family_reliability",
        "rolling_odds_bucket_reliability",
    ],
    "entropy": [
        "avg_ecse_entropy",
        "median_entropy",
        "pct_model_conflict",
        "pct_high_goal_shift",
        "confidence_dispersion",
    ],
    "coverage": [
        "avg_primary_covered_mass",
        "avg_final_covered_mass",
        "avg_residual_risk",
        "exact_score_concentration",
        "coupon_diversification_score",
        "coupon_overlap_score",
    ],
    "insurance": [
        "avg_insurance_gain",
        "total_insurance_tickets",
        "avg_insurance_legs",
        "rolling_insurance_rescue_rate",
    ],
    "odds": [
        "avg_favorite_odds",
        "median_favorite_odds",
        "avg_draw_odds",
        "avg_combined_odds",
        "pct_manually_transcribed_odds",
        "odds_freshness_score",
        "odds_volatility_proxy",
    ],
    "timing": [
        "avg_kickoff_distance_hours",
        "kickoff_time_concentration",
        "simultaneous_kickoff_count",
        "evening_vs_daytime_ratio",
        "rolling_dow_reliability",
        "rolling_month_phase",
    ],
    "historical_rolling": [
        "rolling_league_reliability",
        "rolling_market_family_reliability",
        "rolling_odds_bucket_reliability",
        "rolling_dow_reliability",
        "rolling_month_phase",
        "rolling_model_calibration",
        "rolling_insurance_rescue_rate",
        "rolling_complete_coupon_failure_rate",
    ],
    "prediction_quality": [
        "avg_wde_confidence",
        "median_wde_confidence",
        "min_wde_confidence",
        "max_wde_confidence",
        "avg_top5_mass",
        "min_top5_mass",
        "pct_no_bet",
        "pct_consensus_high",
        "pct_full_super_consensus",
        "pct_canonical_exact_v2_agreement",
        "rolling_model_calibration",
    ],
    "slate": [
        "n_discovered_fixtures",
        "n_eligible_fixtures",
        "n_selected_fixtures",
        "pct_tier_s",
        "pct_tier_a",
        "pct_tier_b",
        "pct_tier_lower",
        "total_main_tickets",
        "capital_concentration_baseline",
        "capital_concentration_calibrated",
    ],
}
