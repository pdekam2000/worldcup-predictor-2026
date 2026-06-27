"""Combo assembly with conflict detection — Phase A17."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.betting_plan.constants import COMBO_SPECS, CONFLICT_GROUPS


def _norm_sel(value: Any) -> str:
    return str(value or "").lower().replace(" ", "_")


def has_conflict(existing: list[dict[str, Any]], candidate: dict[str, Any]) -> bool:
    c_sel = _norm_sel(candidate.get("prediction") or candidate.get("selection"))
    c_market = _norm_sel(candidate.get("market"))
    for leg in existing:
        l_sel = _norm_sel(leg.get("prediction") or leg.get("selection"))
        same_fixture = leg.get("fixture_id") == candidate.get("fixture_id")
        if same_fixture:
            for group in CONFLICT_GROUPS:
                if c_sel in group and l_sel in group and c_sel != l_sel:
                    return True
            if _norm_sel(leg.get("market")) == c_market and l_sel != c_sel:
                return True
    return False


def is_correlated(existing: list[dict[str, Any]], candidate: dict[str, Any]) -> bool:
    same_league = [
        l
        for l in existing
        if l.get("competition_key") and l.get("competition_key") == candidate.get("competition_key")
    ]
    if len(same_league) >= 4:
        return True
    for leg in existing:
        if leg.get("fixture_id") == candidate.get("fixture_id") and _norm_sel(leg.get("market")) == _norm_sel(
            candidate.get("market")
        ):
            return True
    return False


def build_combo(
    legs: list[dict[str, Any]],
    combo_type: str,
    *,
    prioritize_value: bool = False,
) -> dict[str, Any]:
    spec = COMBO_SPECS.get(combo_type, COMBO_SPECS["balanced"])
    min_q = float(spec["min_quality"])
    min_legs = int(spec["min_legs"])
    max_legs = int(spec["max_legs"])

    candidates = [l for l in legs if float(l.get("bet_quality_score") or 0) >= min_q]
    if prioritize_value:
        candidates.sort(
            key=lambda x: (
                float(x.get("odds_decimal") or 0),
                float(x.get("bet_quality_score") or 0),
            ),
            reverse=True,
        )
    else:
        candidates.sort(key=lambda x: float(x.get("bet_quality_score") or 0), reverse=True)

    selected: list[dict[str, Any]] = []
    reject_reasons: dict[str, int] = {}

    for cand in candidates:
        if len(selected) >= max_legs:
            break
        if has_conflict(selected, cand):
            reject_reasons["conflict"] = reject_reasons.get("conflict", 0) + 1
            continue
        if is_correlated(selected, cand):
            reject_reasons["correlation"] = reject_reasons.get("correlation", 0) + 1
            continue
        selected.append(cand)

    quality_scores = [float(l.get("bet_quality_score") or 0) for l in selected]
    combined_quality = round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else None
    odds_list = [float(l["odds_decimal"]) for l in selected if l.get("odds_decimal") and float(l["odds_decimal"]) > 1]
    combined_odds = round(_product(odds_list), 2) if odds_list else None
    missing_odds = any(not l.get("odds_decimal") for l in selected)
    has_caution = any(l.get("caution") for l in selected)

    empty_reason = None
    if len(selected) < min_legs:
        if len(candidates) < min_legs:
            empty_reason = "not_enough_eligible_legs"
        elif reject_reasons.get("conflict", 0) > 0:
            empty_reason = "too_many_conflicts"
        elif reject_reasons.get("correlation", 0) > 0:
            empty_reason = "too_many_correlated_legs"
        else:
            empty_reason = "quality_too_low"

    return {
        "type": combo_type,
        "label": spec["label"],
        "risk": spec["risk"],
        "legs": selected,
        "leg_count": len(selected),
        "combined_quality": combined_quality,
        "combined_odds": combined_odds,
        "missing_odds_warning": missing_odds and bool(selected),
        "odds_estimated": any(l.get("odds_estimated") for l in selected),
        "caution_warning": "Includes caution — best available legs" if has_caution else None,
        "empty_reason": empty_reason if len(selected) < min_legs else None,
        "eligible_candidate_count": len(candidates),
        "reject_reasons": reject_reasons,
    }


def _product(values: list[float]) -> float:
    out = 1.0
    for v in values:
        out *= v
    return out


def build_all_combos(legs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        "safe": build_combo(legs, "safe"),
        "balanced": build_combo(legs, "balanced"),
        "value": build_combo(legs, "value", prioritize_value=True),
        "high_odds": build_combo(legs, "high_odds", prioritize_value=True),
    }
