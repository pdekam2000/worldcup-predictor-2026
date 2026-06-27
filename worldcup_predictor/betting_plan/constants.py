"""Betting plan constants — Phase A17."""

from __future__ import annotations

SINGLE_CATEGORIES: tuple[tuple[str, float, float | None], ...] = (
    ("elite", 90.0, None),
    ("strong", 80.0, 89.9),
    ("good", 70.0, 79.9),
    ("risky", 45.0, 69.9),
    ("avoid", 0.0, 44.9),
)

COMBO_SPECS: dict[str, dict] = {
    "safe": {
        "label": "SAFE COMBO",
        "min_quality": 90.0,
        "min_legs": 2,
        "max_legs": 4,
        "risk": "Low",
    },
    "balanced": {
        "label": "BALANCED COMBO",
        "min_quality": 75.0,
        "min_legs": 3,
        "max_legs": 5,
        "risk": "Medium",
    },
    "value": {
        "label": "VALUE COMBO",
        "min_quality": 60.0,
        "min_legs": 3,
        "max_legs": 6,
        "risk": "Medium",
    },
    "high_odds": {
        "label": "HIGH ODDS COMBO",
        "min_quality": 45.0,
        "min_legs": 4,
        "max_legs": 8,
        "risk": "High",
    },
}

RISK_PROFILES: dict[str, dict[str, tuple[float, float]]] = {
    "conservative": {
        "single": (0.005, 0.01),
        "combo": (0.005, 0.02),
    },
    "balanced": {
        "single": (0.01, 0.02),
        "combo": (0.01, 0.04),
    },
    "aggressive": {
        "single": (0.02, 0.04),
        "combo": (0.02, 0.08),
    },
}

DAY_QUALITY_LABELS = ("Excellent", "Good", "Risky", "Poor")

CONFLICT_GROUPS: tuple[tuple[str, ...], ...] = (
    ("home_win", "home", "away_win", "away", "draw", "1", "2", "x"),
    ("over_2_5", "under_2_5", "over_1_5", "under_1_5", "over", "under"),
    ("yes", "no", "btts_yes", "btts_no"),
)
