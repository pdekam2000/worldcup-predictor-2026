"""ESLI league policy (esli-policy-v1) — versioned, read-only.

League tier evidence is the frozen output of the ESLI read-only audit
(n=94 forward-evaluated fixtures). This module ONLY classifies leagues and
fixtures into selection-eligibility classes. It contains no canonical logic.
"""
from __future__ import annotations

POLICY_VERSION = "esli-policy-v1"
MIN_SAMPLE = 5  # forward fixtures required to leave PROVISIONAL

# Measured ESLI evidence set (immutable research audit). score = 0..100 stability score.
LEAGUE_EVIDENCE: dict[str, dict] = {
    "europa_league":     {"tier": "S", "n": 6,  "score": 69.4, "t1": 0.167, "t3": 0.500, "t5": 0.667, "t10": 0.833, "top5_mass": 0.5864, "entropy": 2.1819, "tail_risk": 0.167, "direction_reversal": 0.500, "bookmaker_coverage": 13.0},
    "allsvenskan":       {"tier": "A", "n": 8,  "score": 67.9, "t1": 0.250, "t3": 0.500, "t5": 0.625, "t10": 0.750, "top5_mass": 0.4960, "entropy": 2.2324, "tail_risk": 0.000, "direction_reversal": 0.250, "bookmaker_coverage": 11.75},
    "conference_league": {"tier": "A", "n": 16, "score": 65.5, "t1": 0.250, "t3": 0.562, "t5": 0.750, "t10": 0.875, "top5_mass": 0.5171, "entropy": 2.2358, "tail_risk": 0.125, "direction_reversal": 0.500, "bookmaker_coverage": 12.95},
    "champions_league":  {"tier": "B", "n": 17, "score": 57.9, "t1": 0.118, "t3": 0.353, "t5": 0.529, "t10": 0.706, "top5_mass": 0.5431, "entropy": 2.2046, "tail_risk": 0.176, "direction_reversal": 0.412, "bookmaker_coverage": 13.0},
    "world_cup_2026":    {"tier": "B", "n": 24, "score": 54.7, "t1": 0.125, "t3": 0.417, "t5": 0.625, "t10": 0.833, "top5_mass": 0.5711, "entropy": 2.1954, "tail_risk": 0.083, "direction_reversal": 0.458, "bookmaker_coverage": 0.0},
    "veikkausliiga":     {"tier": "B", "n": 3,  "score": 54.3, "t1": 0.333, "t3": 0.333, "t5": 0.333, "t10": 1.000, "top5_mass": 0.5020, "entropy": 2.2309, "tail_risk": 0.000, "direction_reversal": 0.667, "bookmaker_coverage": 11.17},
    "one_lyga":          {"tier": "B", "n": 4,  "score": 53.3, "t1": 0.250, "t3": 0.250, "t5": 0.250, "t10": 0.500, "top5_mass": 0.7087, "entropy": 2.0703, "tail_risk": 0.250, "direction_reversal": 0.250, "bookmaker_coverage": 2.6},
    "a_lyga":            {"tier": "B", "n": 3,  "score": 49.0, "t1": 0.000, "t3": 0.333, "t5": 0.333, "t10": 0.667, "top5_mass": 0.7220, "entropy": 2.0445, "tail_risk": 0.333, "direction_reversal": 0.667, "bookmaker_coverage": 2.0},
    "virsliga":          {"tier": "C", "n": 3,  "score": 46.2, "t1": 0.000, "t3": 0.333, "t5": 0.333, "t10": 0.667, "top5_mass": 0.5340, "entropy": 2.2189, "tail_risk": 0.000, "direction_reversal": 0.333, "bookmaker_coverage": 2.0},
    "superettan":        {"tier": "C", "n": 5,  "score": 44.0, "t1": 0.000, "t3": 0.400, "t5": 0.400, "t10": 0.600, "top5_mass": 0.4742, "entropy": 2.2515, "tail_risk": 0.400, "direction_reversal": 0.400, "bookmaker_coverage": 9.67},
    "urvalsdeild":       {"tier": "D", "n": 4,  "score": 23.9, "t1": 0.000, "t3": 0.000, "t5": 0.000, "t10": 0.500, "top5_mass": 0.4424, "entropy": 2.2560, "tail_risk": 0.500, "direction_reversal": 0.250, "bookmaker_coverage": 8.6},
    "one_deild":         {"tier": "D", "n": 1,  "score": 22.3, "t1": 0.000, "t3": 0.000, "t5": 0.000, "t10": 0.000, "top5_mass": 0.4745, "entropy": 2.2379, "tail_risk": 1.000, "direction_reversal": 0.000, "bookmaker_coverage": 7.5},
}


def classify_league(league_key: str) -> dict:
    """Return ESLI classification for a canonical league key. Read-only."""
    ev = LEAGUE_EVIDENCE.get(league_key)
    if ev is None:
        return {"eligibility_class": "ESLI_UNMEASURED", "tier": None, "n": 0, "score": None,
                "provisional": None, "evidence": None}
    n = ev["n"]
    tier = ev["tier"]
    provisional = n < MIN_SAMPLE
    if provisional:
        cls = "ESLI_PROVISIONAL"
    elif tier in ("S", "A"):
        cls = "ESLI_STRONG"
    elif tier == "B":
        cls = "ESLI_CONDITIONAL"
    else:  # C, D with n >= MIN_SAMPLE
        cls = "ESLI_AVOID_PRIMARY_EXACT"
    return {"eligibility_class": cls, "tier": tier, "n": n, "score": ev["score"],
            "provisional": provisional, "evidence": ev}


# Composite ranking weights (Part J) — research/selection ONLY, never alters canonical output.
COMPOSITE_WEIGHTS = {
    "esli_suitability": 0.25,
    "top5_mass": 0.20,
    "top3_mass": 0.10,
    "top1_prob": 0.05,
    "low_entropy": 0.10,
    "wde_ecse_agreement": 0.10,
    "low_tail_risk": 0.05,
    "low_direction_reversal": 0.05,
    "data_quality": 0.05,
    "book_freshness": 0.05,
}

# Normalization anchors (documented; domain ranges observed in immutable data).
ANCHORS = {
    "esli_score": (40.0, 70.0),
    "top5_mass": (0.45, 0.80),
    "top3_mass": (0.30, 0.55),
    "top1_prob": (0.10, 0.25),
    "entropy_fixture": (1.50, 1.61),   # per-fixture ECSE entropy range
    "league_tail": (0.0, 0.50),
    "league_reversal": (0.0, 0.60),
    "bookmaker": (0.0, 13.0),
}

# Strict Tier-B fixture gates (Part I).
TIER_B_GATES = {
    "min_top5_mass": 0.55,
    "require_high_agreement": True,
    "require_wde_ecse_agreement": True,
    "require_wde_ft_agreement": True,
    "max_entropy_fixture": 1.61,
    "require_fresh_odds": True,
    "min_bookmaker_count": 8,
}
