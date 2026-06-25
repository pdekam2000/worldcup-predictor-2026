"""Rule A conditional harmonization policy — Phase 47C."""

from __future__ import annotations

from typing import Literal

OneXTwoSelection = Literal["home_win", "draw", "away_win"]
HarmonizationSource = Literal["wde", "scoreline"]
HarmonizationReason = Literal[
    "rule_a_odds_present",
    "rule_a_odds_absent",
    "unconditional",
    "no_conflict",
]


def resolve_rule_a_1x2(
    *,
    wde_selection: OneXTwoSelection,
    scoreline_implied: OneXTwoSelection,
    odds_available: bool,
    conditional_enabled: bool,
) -> tuple[OneXTwoSelection, bool, HarmonizationSource, HarmonizationReason]:
    """
    Rule A: odds present → scoreline-implied 1X2; odds absent → WDE 1X2.

    Returns (final_1x2, harmonization_used, harmonization_source, harmonization_reason).
    harmonization_used is True when the published 1X2 follows scoreline harmonization.
    """
    if not conditional_enabled:
        used = wde_selection != scoreline_implied
        return (
            scoreline_implied,
            used,
            "scoreline",
            "no_conflict" if not used else "unconditional",
        )

    if odds_available:
        used = True
        if wde_selection == scoreline_implied:
            return scoreline_implied, False, "scoreline", "no_conflict"
        return scoreline_implied, True, "scoreline", "rule_a_odds_present"

    if wde_selection == scoreline_implied:
        return wde_selection, False, "wde", "no_conflict"
    return wde_selection, False, "wde", "rule_a_odds_absent"
