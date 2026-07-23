"""ESLI FORWARD SHADOW assessment + composite ranking + Top3 combo generation.

READ-ONLY over canonical artifacts. Consumes an immutable canonical prediction
record (as produced by the canonical WDE/ECSE/BTTS/O-U pipeline and frozen) and
emits a *separate* ESLI shadow assessment. Never mutates the canonical payload.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from itertools import product
from datetime import datetime, timezone
from typing import Any

from . import (MODEL_ID, MODEL_NAME, MODEL_VERSION, STATUS, IS_SHADOW,
               PUBLIC_VISIBLE, FINAL_DECISION_AUTHORITY, RESEARCH_SOURCE)
from .policy import (classify_league, COMPOSITE_WEIGHTS, ANCHORS, TIER_B_GATES,
                     POLICY_VERSION)


def _norm(v: float, lo: float, hi: float) -> float:
    if v is None:
        return 0.0
    if hi == lo:
        return 0.0
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def selection_effect(cls: str) -> str:
    return {
        "ESLI_STRONG": "PRIMARY_EXACT_ELIGIBLE",
        "ESLI_CONDITIONAL": "CONDITIONAL_EXACT_ELIGIBLE",
        "ESLI_AVOID_PRIMARY_EXACT": "AVOID_PRIMARY_EXACT",
        "ESLI_PROVISIONAL": "PROVISIONAL_INSUFFICIENT_SAMPLE",
        "ESLI_UNMEASURED": "UNMEASURED_LEAGUE",
    }[cls]


@dataclass
class EsliAssessment:
    fixture_id: int
    date: str
    league: str
    canonical_league_key: str
    esli_score: float | None
    esli_tier: str | None
    sample_size: int
    eligibility_class: str
    policy_version: str
    generated_at: str
    linked_canonical_freeze_id: str | None
    linked_canonical_freeze_hash: str | None
    selection_effect: str
    warnings: list = field(default_factory=list)
    # research-only diagnostics (NOT serialized into canonical output)
    composite_score: float | None = None
    composite_components: dict = field(default_factory=dict)


def assess_fixture(rec: dict, date: str) -> EsliAssessment:
    lk = rec.get("competition")
    cls = classify_league(lk)
    ev = cls["evidence"] or {}
    fr = rec.get("freeze") or {}
    warnings: list[str] = []
    if cls["eligibility_class"] == "ESLI_UNMEASURED":
        warnings.append("league_absent_from_esli_evidence")
    if cls["eligibility_class"] == "ESLI_PROVISIONAL":
        warnings.append(f"provisional_sample_n={cls['n']}")
    return EsliAssessment(
        fixture_id=rec.get("fixture_id"),
        date=date,
        league=rec.get("league") or lk,
        canonical_league_key=lk,
        esli_score=cls["score"],
        esli_tier=cls["tier"],
        sample_size=cls["n"],
        eligibility_class=cls["eligibility_class"],
        policy_version=POLICY_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
        linked_canonical_freeze_id=fr.get("freeze_id"),
        linked_canonical_freeze_hash=fr.get("content_hash"),
        selection_effect=selection_effect(cls["eligibility_class"]),
        warnings=warnings,
    )


def composite(rec: dict, cls: dict) -> tuple[float, dict]:
    """Research-only composite score (Part J). Does not alter canonical output."""
    ev = cls["evidence"] or {}
    ecse = rec.get("ecse") or {}
    comp = {
        "esli_suitability": _norm(cls.get("score") or 0, *ANCHORS["esli_score"]),
        "top5_mass": _norm(ecse.get("top5_mass"), *ANCHORS["top5_mass"]),
        "top3_mass": _norm(ecse.get("top3_mass"), *ANCHORS["top3_mass"]),
        "top1_prob": _norm(ecse.get("top1_probability"), *ANCHORS["top1_prob"]),
        "low_entropy": 1.0 - _norm(ecse.get("entropy"), *ANCHORS["entropy_fixture"]),
        "wde_ecse_agreement": 1.0 if rec.get("wde_ecse_agreement") else 0.0,
        "low_tail_risk": 1.0 - _norm(ev.get("tail_risk", 0.5), *ANCHORS["league_tail"]),
        "low_direction_reversal": 1.0 - _norm(ev.get("direction_reversal", 0.6), *ANCHORS["league_reversal"]),
        "data_quality": (rec.get("data_quality") or 0) / 100.0,
        "book_freshness": _norm((rec.get("odds") or {}).get("bookmaker_count", 0), *ANCHORS["bookmaker"]),
    }
    score = sum(comp[k] * COMPOSITE_WEIGHTS[k] for k in COMPOSITE_WEIGHTS) * 100.0
    return round(score, 2), {k: round(v, 4) for k, v in comp.items()}


def primary_gates_pass(rec: dict) -> tuple[bool, list[str]]:
    """Part H required fixture gates (for ESLI_STRONG primary eligibility)."""
    fails = []
    if rec.get("fixture_status") != "NS":
        fails.append("not_prematch")
    if rec.get("eligibility") != "PREDICTION_ELIGIBLE":
        fails.append("not_prediction_eligible")
    if not rec.get("prediction_complete"):
        fails.append("prediction_incomplete")
    odds = rec.get("odds") or {}
    if not odds.get("complete") or odds.get("freshness_status") != "ODDS_FRESH":
        fails.append("odds_not_fresh_complete")
    ecse = rec.get("ecse") or {}
    if not all(ecse.get(f"top{i}") for i in range(1, 6)):
        fails.append("ecse_top5_missing")
    if not (rec.get("freeze") or {}).get("freeze_id"):
        fails.append("no_valid_freeze")
    if rec.get("consensus") == "HIGH_CONFLICT" or not rec.get("wde_ecse_agreement"):
        fails.append("high_conflict")
    if (rec.get("data_quality") or 0) < 70:
        fails.append("low_data_quality")
    if (rec.get("mapping_confidence") or "").upper() in ("LOW", "NONE"):
        fails.append("severe_mapping_warning")
    return (len(fails) == 0), fails


def tier_b_gates_pass(rec: dict) -> tuple[bool, list[str]]:
    """Part I strict Tier-B gates."""
    fails = []
    ecse = rec.get("ecse") or {}
    if (ecse.get("top5_mass") or 0) < TIER_B_GATES["min_top5_mass"]:
        fails.append("top5_mass_below_0.55")
    if rec.get("consensus") != "HIGH_AGREEMENT":
        fails.append("not_high_agreement")
    if not rec.get("wde_ecse_agreement"):
        fails.append("wde_ecse_disagreement")
    if not rec.get("wde_ft_agreement"):
        fails.append("wde_ft_disagreement")
    if (ecse.get("entropy") or 99) > TIER_B_GATES["max_entropy_fixture"]:
        fails.append("entropy_too_high")
    odds = rec.get("odds") or {}
    if odds.get("freshness_status") != "ODDS_FRESH":
        fails.append("odds_not_fresh")
    if (odds.get("bookmaker_count") or 0) < TIER_B_GATES["min_bookmaker_count"]:
        fails.append("insufficient_bookmaker_coverage")
    return (len(fails) == 0), fails


def top3_scores(rec: dict) -> list[dict]:
    ecse = rec.get("ecse") or {}
    return [{"rank": ecse[f"top{i}"]["rank"], "score": ecse[f"top{i}"]["score"],
             "probability": ecse[f"top{i}"]["probability"]} for i in range(1, 4)]


def top5_scores(rec: dict) -> list[dict]:
    ecse = rec.get("ecse") or {}
    return [{"rank": ecse[f"top{i}"]["rank"], "score": ecse[f"top{i}"]["score"],
             "probability": ecse[f"top{i}"]["probability"]} for i in range(1, 6)]


def generate_27_combos(three: list[dict]) -> list[dict]:
    """3 x 3 x 3 = 27 combinations from the canonical Top3 of three fixtures.
    NO manual hedge scores. NO Top4/Top5 usage."""
    tops = [top3_scores(r) for r in three]
    combos = []
    for i, (a, b, c) in enumerate(product(tops[0], tops[1], tops[2]), start=1):
        joint = a["probability"] * b["probability"] * c["probability"]
        combos.append({
            "n": i,
            "match_a": a["score"], "match_b": b["score"], "match_c": c["score"],
            "joint_probability_independent": round(joint, 6),
        })
    return combos


def joint_coverage(three: list[dict]) -> dict:
    """Estimated joint coverage under an independence assumption (Part M)."""
    t3 = 1.0
    t5 = 1.0
    for r in three:
        ecse = r.get("ecse") or {}
        t3 *= (ecse.get("top3_mass") or 0)
        t5 *= (ecse.get("top5_mass") or 0)
    return {
        "estimated_joint_top3_coverage": round(t3, 6),
        "estimated_joint_top5_coverage": round(t5, 6),
        "top3_tickets": 27,
        "top5_tickets": 125,
        "independence_warning": ("Joint coverage assumes fixture independence; it is an "
                                 "UPPER-BOUND ESTIMATE, NOT a guaranteed win rate."),
    }


def registry_record() -> dict:
    return {
        "model_id": MODEL_ID, "model_name": MODEL_NAME, "model_version": MODEL_VERSION,
        "status": STATUS, "is_shadow": IS_SHADOW, "public_visible": PUBLIC_VISIBLE,
        "final_decision_authority": FINAL_DECISION_AUTHORITY,
        "policy_version": POLICY_VERSION, "research_source": RESEARCH_SOURCE,
    }
