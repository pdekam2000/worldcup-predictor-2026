"""PHASE ECSE-X2-M2 — Candidate market algebra equations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

from worldcup_predictor.research.ecse_x2_m2.constants import PHI_TARGETS


def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den <= 1e-9:
        return None
    return num / den


def _avg(*vals: float | None) -> float | None:
    clean = [v for v in vals if v is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _abs_diff(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return abs(a - b)


@dataclass(frozen=True)
class EquationSpec:
    key: str
    label: str
    required: tuple[str, ...]
    compute: Callable[[dict[str, float | None]], float | None]


def _specs() -> list[EquationSpec]:
    p = lambda k: k  # noqa: E731 — readability in lambdas below

    base: list[EquationSpec] = [
        EquationSpec(
            "home_away_over_draw",
            "(home_prob + away_prob) / draw_proxy",
            ("ft_home", "ft_away", "draw_proxy"),
            lambda x: _safe_div((x["ft_home"] or 0) + (x["ft_away"] or 0), x["draw_proxy"]),
        ),
        EquationSpec(
            "over25_over_btts_yes",
            "over25_prob / btts_yes_prob",
            ("ou_over_25", "btts_yes"),
            lambda x: _safe_div(x["ou_over_25"], x["btts_yes"]),
        ),
        EquationSpec(
            "under25_over_btts_no",
            "under25_prob / btts_no_prob",
            ("ou_under_25", "btts_no"),
            lambda x: _safe_div(x["ou_under_25"], x["btts_no"]),
        ),
        EquationSpec(
            "home_away_gap_over_over25",
            "abs(home_prob - away_prob) / over25_prob",
            ("ft_home", "ft_away", "ou_over_25"),
            lambda x: _safe_div(_abs_diff(x["ft_home"], x["ft_away"]), x["ou_over_25"]),
        ),
        EquationSpec(
            "home_o15_minus_away_o05",
            "home_team_o15_prob - away_team_o05_prob",
            ("team_home_over_15", "team_away_over_05"),
            lambda x: (x["team_home_over_15"] - x["team_away_over_05"])
            if x["team_home_over_15"] is not None and x["team_away_over_05"] is not None
            else None,
        ),
        EquationSpec(
            "corners_o85_over_over25",
            "corners_o85_prob / over25_prob",
            ("corner_over_85", "ou_over_25"),
            lambda x: _safe_div(x["corner_over_85"], x["ou_over_25"]),
        ),
        EquationSpec(
            "fh_draw_over_draw_proxy",
            "fh_draw_prob / draw_proxy",
            ("fh_draw", "draw_proxy"),
            lambda x: _safe_div(x["fh_draw"], x["draw_proxy"]),
        ),
        EquationSpec(
            "avg_home_over25_btts_yes",
            "(home_prob + over25_prob + btts_yes_prob) / 3",
            ("ft_home", "ou_over_25", "btts_yes"),
            lambda x: _avg(x["ft_home"], x["ou_over_25"], x["btts_yes"]),
        ),
        EquationSpec(
            "avg_draw_under25_btts_no",
            "(draw_proxy + under25_prob + btts_no_prob) / 3",
            ("draw_proxy", "ou_under_25", "btts_no"),
            lambda x: _avg(x["draw_proxy"], x["ou_under_25"], x["btts_no"]),
        ),
        EquationSpec(
            "over15_over_under35",
            "over15_prob / under35_prob",
            ("ou_over_15", "ou_under_35"),
            lambda x: _safe_div(x["ou_over_15"], x["ou_under_35"]),
        ),
        EquationSpec(
            "btts_yes_times_over25",
            "btts_yes_prob * over25_prob",
            ("btts_yes", "ou_over_25"),
            lambda x: x["btts_yes"] * x["ou_over_25"]
            if x["btts_yes"] is not None and x["ou_over_25"] is not None
            else None,
        ),
        EquationSpec(
            "home_over_away_times_draw",
            "(home_prob / away_prob) * draw_proxy",
            ("ft_home", "ft_away", "draw_proxy"),
            lambda x: _safe_div(x["ft_home"], x["ft_away"]) * x["draw_proxy"]
            if _safe_div(x["ft_home"], x["ft_away"]) is not None and x["draw_proxy"] is not None
            else None,
        ),
        EquationSpec(
            "corner95_minus_over25",
            "corner_over95_prob - over25_prob",
            ("corner_over_95", "ou_over_25"),
            lambda x: x["corner_over_95"] - x["ou_over_25"]
            if x["corner_over_95"] is not None and x["ou_over_25"] is not None
            else None,
        ),
        EquationSpec(
            "fh_home_minus_ft_home",
            "fh_home_prob - ft_home_prob",
            ("fh_home", "ft_home"),
            lambda x: x["fh_home"] - x["ft_home"]
            if x["fh_home"] is not None and x["ft_home"] is not None
            else None,
        ),
    ]

    for phi in PHI_TARGETS:
        base.append(
            EquationSpec(
                f"phi_proximity_{str(phi).replace('.', '')}",
                f"-abs(over25_prob - {phi})",
                ("ou_over_25",),
                lambda x, target=phi: -abs((x["ou_over_25"] or 0) - target)
                if x["ou_over_25"] is not None
                else None,
            )
        )
        base.append(
            EquationSpec(
                f"ratio_home_away_near_{str(phi).replace('.', '')}",
                f"-abs((home_prob/away_prob) - {phi})",
                ("ft_home", "ft_away"),
                lambda x, target=phi: -abs((_safe_div(x["ft_home"], x["ft_away"]) or 0) - target)
                if _safe_div(x["ft_home"], x["ft_away"]) is not None
                else None,
            )
        )

    for stem, label in (
        ("ou_over_25", "over25_prob"),
        ("btts_yes", "btts_yes_prob"),
        ("draw_proxy", "draw_proxy"),
        ("ft_home", "home_prob"),
    ):
        base.append(
            EquationSpec(
                f"golden_{stem}",
                f"log({label}) / log(1.618)",
                (stem,),
                lambda x, s=stem: math.log(max(x[s] or 1e-9, 1e-9)) / math.log(1.618)
                if x[s] is not None
                else None,
            )
        )

    return base


CANDIDATE_EQUATIONS: tuple[EquationSpec, ...] = tuple(_specs())


def compute_equation(spec: EquationSpec, probs: dict[str, float | None]) -> float | None:
    if any(probs.get(k) is None for k in spec.required):
        return None
    try:
        val = spec.compute(probs)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if val is None or not math.isfinite(val):
        return None
    return float(val)
