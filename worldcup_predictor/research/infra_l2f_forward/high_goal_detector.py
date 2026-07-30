"""Research-only prematch high-goal detector (no canonical routing)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from worldcup_predictor.research.infra_l2f_forward.deep_slices import _load_eval_join, _wilson_interval


MIN_COHORT = 15


@dataclass
class DetectorRule:
    name: str
    description: str
    min_expected_total: float = 2.75
    min_tail_mass: float | None = 0.20
    require_balanced: bool | None = None


DEFAULT_RULES = [
    DetectorRule(
        name="et_gte_2_75",
        description="Prematch expected total lambda >= 2.75",
        min_expected_total=2.75,
        min_tail_mass=None,
    ),
    DetectorRule(
        name="et_gte_3_0",
        description="Prematch expected total lambda >= 3.0",
        min_expected_total=3.0,
        min_tail_mass=None,
    ),
    DetectorRule(
        name="et_gte_2_75_and_tail",
        description="Expected total >= 2.75 and ECSE top-list mass on 4+ scores >= 0.20 when available",
        min_expected_total=2.75,
        min_tail_mass=0.20,
    ),
    DetectorRule(
        name="et_gte_2_75_balanced",
        description="Expected total >= 2.75 and balanced 1X2 odds",
        min_expected_total=2.75,
        min_tail_mass=None,
        require_balanced=True,
    ),
]


def _apply_rule(row: dict[str, Any], rule: DetectorRule) -> bool:
    if float(row.get("expected_total_lambda") or 0) < rule.min_expected_total:
        return False
    if rule.require_balanced is True and row.get("balanced_prematch") is not True:
        return False
    if rule.require_balanced is False and row.get("balanced_prematch") is True:
        return False
    if rule.min_tail_mass is not None:
        tm = row.get("ecse_tail_mass_ge4_prematch")
        if tm is None:
            # If tail mass unavailable, do not admit (avoid leakage via missingness tricks)
            return False
        if float(tm) < rule.min_tail_mass:
            return False
    return True


def evaluate_detector(
    eval_conn,
    fi_conn,
    *,
    train_cohorts: list[str] | None = None,
    holdout_true_forward: bool = True,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """
    Develop on historical_replay (+ recovered). Never fit on true_forward.
    Labels for precision/recall of 'high-goal game' use actual totals ONLY for evaluation,
    never as rule inputs.
    """
    train_cohorts = train_cohorts or ["historical_replay", "historical_replay_result_recovered"]
    rows = _load_eval_join(eval_conn, fi_conn, cohort_types=train_cohorts)
    tf_rows = []
    if holdout_true_forward:
        tf_rows = _load_eval_join(eval_conn, fi_conn, cohort_types=["true_forward"])

    results = []
    for rule in DEFAULT_RULES:
        selected = [r for r in rows if _apply_rule(r, rule)]
        n = len(selected)
        if n < MIN_COHORT:
            results.append(
                {
                    "rule": asdict(rule),
                    "n": n,
                    "status": "insufficient_n",
                    "min_required": MIN_COHORT,
                }
            )
            continue

        # High-goal label for recall/precision (evaluation only)
        high = [r for r in selected if int(r.get("actual_total_goals") or 0) >= 4]
        all_high = [r for r in rows if int(r.get("actual_total_goals") or 0) >= 4]
        precision = len(high) / n
        recall = len(high) / len(all_high) if all_high else 0.0
        coverage = n / len(rows) if rows else 0.0

        e5 = sum(int(r["top5"]) for r in selected) / n
        c_hits = [int(r["canonical_top5"]) for r in selected if r.get("canonical_top5") is not None]
        c5 = sum(c_hits) / len(c_hits) if c_hits else None
        uplift = (e5 - c5) if c5 is not None else None

        # Also report within selected high-goal subset (descriptive only)
        high_e5 = sum(int(r["top5"]) for r in high) / len(high) if high else None
        high_c = [int(r["canonical_top5"]) for r in high if r.get("canonical_top5") is not None]
        high_c5 = sum(high_c) / len(high_c) if high_c else None

        results.append(
            {
                "rule": asdict(rule),
                "n": n,
                "status": "ok",
                "coverage": coverage,
                "precision_actual_4plus": precision,
                "recall_actual_4plus": recall,
                "precision_wilson_95": _wilson_interval(len(high), n),
                "exact_v2_top5": e5,
                "canonical_top5": c5,
                "challenger_uplift_top5": uplift,
                "exact_v2_top5_wilson_95": _wilson_interval(sum(int(r["top5"]) for r in selected), n),
                "within_selected_actual_4plus": {
                    "n": len(high),
                    "exact_v2_top5": high_e5,
                    "canonical_top5": high_c5,
                    "note": "Descriptive only; outcome-conditioned — not a routing metric.",
                },
                "inputs_prematch_only": True,
                "labels_use_final_goals": True,
                "routing_activated": False,
            }
        )

    report = {
        "research_only": True,
        "routing_activated": False,
        "train_cohorts": train_cohorts,
        "train_n": len(rows),
        "true_forward_holdout_n": len(tf_rows),
        "true_forward_note": (
            "Reserved untouched for future validation; no rule fitting on true_forward."
            if holdout_true_forward
            else "Holdout disabled"
        ),
        "min_cohort": MIN_COHORT,
        "rules": results,
        "proof_no_final_goals_in_inputs": True,
        "proof_detail": (
            "Detector predicates use expected_total_lambda, balanced odds, and optional "
            "ECSE payload tail mass from freeze-time payloads only. actual_total_goals is "
            "used solely to score precision/recall after selection."
        ),
    }
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
