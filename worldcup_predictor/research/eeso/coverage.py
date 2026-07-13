"""EESO coverage diagnostics — extends Last-8 coverage with standardized flags."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.last8_team_form.coverage_diagnostics import diagnose_top5_coverage
from worldcup_predictor.research.eeso.constants import COVERAGE_FLAG_ALIASES


def normalize_coverage_flags(flags: list[str]) -> list[str]:
    out: list[str] = []
    for flag in flags:
        out.append(COVERAGE_FLAG_ALIASES.get(flag, flag))
    return sorted(set(out))


def diagnose_eeso_top5_coverage(
    top5: list[str] | list[dict[str, Any]],
    *,
    top5_probs: list[float] | None = None,
) -> dict[str, Any]:
    """Run Last-8 coverage diagnostics and emit EESO-standard warning names."""
    diag = diagnose_top5_coverage(top5, top5_probs=top5_probs)
    flags = list(diag.get("coverage_flags") or [])
    normalized = normalize_coverage_flags(flags)

    if diag.get("unique_end_result_directions", 0) <= 1 and len(diag.get("scorelines") or []) >= 5:
        if "TOP5_UNDER_DIVERSIFIED" not in normalized:
            normalized.append("TOP5_UNDER_DIVERSIFIED")

    if diag.get("btts_scenario_count", 0) == 0 and diag.get("scorelines"):
        if "ALL_TOP5_BTTS_NO" not in normalized:
            normalized.append("ALL_TOP5_BTTS_NO")

    diag["coverage_flags"] = sorted(set(normalized))
    diag["coverage_flags_raw"] = flags
    return diag


__all__ = ["diagnose_eeso_top5_coverage", "diagnose_top5_coverage", "normalize_coverage_flags"]
