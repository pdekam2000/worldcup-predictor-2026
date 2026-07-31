"""Adaptive Insurance family research (research-only — does not modify production)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _bucket(v: float | None, edges: list[float], labels: list[str]) -> str:
    if v is None:
        return "unknown"
    for i, e in enumerate(edges):
        if v < e:
            return labels[i]
    return labels[-1]


def run_adaptive_insurance_research(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Learn which insurance family performs best under condition slices.
    Output is advisory only — production Insurance policy unchanged.
    """
    # Condition features
    slices: dict[str, dict[str, dict[str, Any]]] = defaultdict(
        lambda: defaultdict(lambda: {"n": 0, "rescues": 0, "wins": 0})
    )

    for fx in fixtures:
        fam = str(fx.get("insurance_market_label") or "NONE")
        conf_b = _bucket(fx.get("confidence"), [0.35, 0.5, 0.65], ["low", "mid", "high", "very_high"])
        ent_b = _bucket(fx.get("entropy"), [2.0, 2.5, 3.0], ["low", "mid", "high", "very_high"])
        fav = fx.get("odds_home")
        fav_b = _bucket(fav, [1.6, 2.2, 3.0], ["strong_fav", "mild_fav", "balanced", "dog_lean"])
        goals_b = _bucket(fx.get("lambda_total"), [2.2, 2.8, 3.4], ["low", "mid", "high", "very_high"])
        league = str(fx.get("league") or "unknown")

        conditions = [
            f"confidence:{conf_b}",
            f"entropy:{ent_b}",
            f"favorite:{fav_b}",
            f"goals:{goals_b}",
            f"league:{league}",
        ]
        exact3 = list(fx.get("exact3") or [])
        main = exact3 + list(fx.get("main_coverage_scores") or [])
        ins = main + list(fx.get("insurance_scores") or [])
        actual = str(fx["actual_score"]).replace(" ", "")
        main_hit = actual in {str(s).replace(" ", "") for s in main}
        ins_hit = actual in {str(s).replace(" ", "") for s in ins}
        rescue = (not main_hit) and ins_hit
        win = actual in {str(s).replace(" ", "") for s in (fx.get("insurance_scores") or [])}

        for cond in conditions:
            cell = slices[cond][fam]
            cell["n"] += 1
            if rescue:
                cell["rescues"] += 1
            if win:
                cell["wins"] += 1

    recommendations = []
    for cond, fams in slices.items():
        ranked = sorted(
            (
                {
                    "family": fam,
                    "n": v["n"],
                    "rescue_rate": round(v["rescues"] / v["n"], 8) if v["n"] else 0.0,
                    "win_rate": round(v["wins"] / v["n"], 8) if v["n"] else 0.0,
                }
                for fam, v in fams.items()
                if v["n"] >= 5
            ),
            key=lambda x: (-x["rescue_rate"], -x["n"]),
        )
        if ranked:
            recommendations.append(
                {
                    "condition": cond,
                    "recommended_insurance_family": ranked[0]["family"],
                    "candidates": ranked[:5],
                }
            )

    recommendations.sort(key=lambda r: r["condition"])
    return {
        "research_only": True,
        "production_logic_modified": False,
        "n_condition_slices": len(recommendations),
        "recommendations": recommendations,
        "note": "Advisory mapping only. Do not wire into production Insurance selection without a later phase.",
    }
