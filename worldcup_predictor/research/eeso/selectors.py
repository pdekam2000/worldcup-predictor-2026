"""EESO shadow selectors — thin wrappers over Last-8 shadow selection."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.last8_team_form.shadow_selector import (
    select_baseline_top5,
    select_hybrid_top5,
    select_last8_aware_top5,
    select_scenario_diversified_top5,
    select_top3_variants,
    select_wde_aligned_top5,
    shadow_selection_bundle,
)


def select_canonical_top1(distribution: list[dict[str, Any]]) -> str:
    lines = select_baseline_top5(distribution)
    return lines[0] if lines else ""


def select_canonical_top3(distribution: list[dict[str, Any]]) -> list[str]:
    return select_baseline_top5(distribution)[:3]


def select_canonical_top5(distribution: list[dict[str, Any]]) -> list[str]:
    return select_baseline_top5(distribution)


def select_probability_only_top5(distribution: list[dict[str, Any]]) -> list[str]:
    """Alias for pure probability ranking (identical to canonical Top5)."""
    return select_baseline_top5(distribution)


def eeso_selection_bundle(
    distribution: list[dict[str, Any]],
    *,
    scenario_profile: dict[str, Any] | None = None,
    wde_direction: str | None = None,
    odds_home: float | None = None,
    odds_draw: float | None = None,
    odds_away: float | None = None,
) -> dict[str, Any]:
    """Expose canonical + shadow selections with explicit EESO naming."""
    bundle = shadow_selection_bundle(
        distribution,
        scenario_profile=scenario_profile,
        wde_direction=wde_direction,
        odds_home=odds_home,
        odds_draw=odds_draw,
        odds_away=odds_away,
    )
    canonical_top5 = bundle["canonical_top5"]
    return {
        **bundle,
        "eeso_shadow_only": True,
        "canonical_top1": canonical_top5[0] if canonical_top5 else None,
        "canonical_top3": canonical_top5[:3],
        "canonical_top5": canonical_top5,
        "eeso_shadow_top5": bundle["shadow_last8_top5"],
        "selectors": {
            "canonical_top1": canonical_top5[0] if canonical_top5 else None,
            "canonical_top3": canonical_top5[:3],
            "canonical_top5": canonical_top5,
            "probability_only": select_probability_only_top5(distribution),
            "wde_aligned": bundle["methods"]["wde_aligned"],
            "last8_aware": bundle["methods"]["last8_aware"],
            "scenario_diversified": bundle["methods"]["scenario_diversified"],
            "hybrid": bundle["methods"]["hybrid"],
        },
        "top3_variants": bundle["top3_variants"],
    }


__all__ = [
    "select_canonical_top1",
    "select_canonical_top3",
    "select_canonical_top5",
    "select_probability_only_top5",
    "select_baseline_top5",
    "select_wde_aligned_top5",
    "select_last8_aware_top5",
    "select_scenario_diversified_top5",
    "select_hybrid_top5",
    "select_top3_variants",
    "eeso_selection_bundle",
    "shadow_selection_bundle",
]
