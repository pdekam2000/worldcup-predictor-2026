"""Validate insurance picks vs alternatives (research-only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.insurance.schemas import (
    InsuranceCandidate,
    UncoveredMassReport,
)
from worldcup_predictor.research.bet_coverage_optimizer.models import CoverageRecommendation
from worldcup_predictor.research.bet_coverage_optimizer.phase4.coverage_explanation import (
    alternative_market_scorelines,
)
from worldcup_predictor.research.bet_coverage_optimizer.score_mapping import covered_scores_for_market


_ALT_SPECS: list[tuple[str, str, dict[str, Any]]] = [
    ("BTTS Yes", "btts", {"side": "yes"}),
    ("BTTS No", "btts", {"side": "no"}),
    ("Win to Nil Home", "win_to_nil", {"team": "home"}),
    ("Win to Nil Away", "win_to_nil", {"team": "away"}),
    ("Over 2.5", "over_under", {"direction": "over", "line": 2.5}),
    ("Under 2.5", "over_under", {"direction": "under", "line": 2.5}),
    ("Over 3.5", "over_under", {"direction": "over", "line": 3.5}),
    ("Under 3.5", "over_under", {"direction": "under", "line": 3.5}),
    ("Winning Margin Home by 1", "winning_margin", {"selection": "home_by_1"}),
    ("Winning Margin Away by 1", "winning_margin", {"selection": "away_by_1"}),
    ("Winning Margin Home by 2", "winning_margin", {"selection": "home_by_2"}),
    ("Double Chance 1X", "double_chance", {"side": "1x"}),
    ("Double Chance X2", "double_chance", {"side": "x2"}),
    ("Home Win & Under 3.5", "result_total", {"result": "home", "direction": "under", "line": 3.5}),
    ("Away Win & Under 3.5", "result_total", {"result": "away", "direction": "under", "line": 3.5}),
]


def _inc_mass(scores: list[str], uncovered: UncoveredMassReport) -> float:
    umap = {u.score: float(u.probability) for u in uncovered.primary_uncovered_scores}
    return round(sum(umap.get(s, 0.0) for s in scores), 8)


def validate_insurance_for_fixture(
    rec: CoverageRecommendation,
    *,
    uncovered: UncoveredMassReport,
    ranked: list[InsuranceCandidate],
) -> dict[str, Any]:
    top_scores = [s.score for s in rec.top_n_scores_list]
    top_map = {s.score: float(s.probability or 0.0) for s in rec.top_n_scores_list}
    elig = [c for c in ranked if c.eligible]
    pick = elig[0] if elig else None

    reduces = False
    overlap_too_much = None
    if pick is not None:
        reduces = float(pick.incremental_uncovered_probability_mass or 0.0) > 0.0
        overlap_too_much = float(pick.primary_overlap_ratio or 0.0) > 0.85

    alternatives: list[dict[str, Any]] = []
    uncovered_set = {u.score for u in uncovered.primary_uncovered_scores}

    def _push_alt(label: str, mt: str, params: dict[str, Any], covered: list[str]) -> None:
        uncovered_hits = [s for s in covered if s in uncovered_set]
        inc = _inc_mass(uncovered_hits, uncovered)
        primary_overlap = round(
            sum(top_map.get(s, 0.0) for s in covered if s not in set(uncovered_hits)), 8
        )
        alternatives.append(
            {
                "label": label,
                "market_type": mt,
                "market_parameters": params,
                "covered_uncovered_scorelines": sorted(uncovered_hits),
                "incremental_uncovered_mass": inc,
                "primary_overlap_mass": primary_overlap,
                "better_than_selected": bool(
                    pick is not None
                    and inc > float(pick.incremental_uncovered_probability_mass or 0.0) + 1e-9
                ),
            }
        )

    for label, mt, params in _ALT_SPECS:
        try:
            covered = covered_scores_for_market(mt, params, top_scores) or []
        except Exception:
            covered = alternative_market_scorelines(
                market_type=mt, market_parameters=params, top_n_scores=top_scores
            )
        _push_alt(label, mt, params, list(covered))

    # Win & BTTS (composed — no dedicated market_type in settlement map)
    for side, label in (("home", "Home Win & BTTS Yes"), ("away", "Away Win & BTTS Yes")):
        composed = []
        for s in top_scores:
            parts = str(s).replace(" ", "").split("-")
            if len(parts) != 2:
                continue
            try:
                hg, ag = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            if hg == 0 or ag == 0:
                continue
            if side == "home" and hg > ag:
                composed.append(s)
            if side == "away" and ag > hg:
                composed.append(s)
        _push_alt(label, "composed_result_btts", {"result": side, "btts": "yes"}, composed)
    alternatives.sort(key=lambda a: (-float(a["incremental_uncovered_mass"]), a["label"]))
    better = [a for a in alternatives if a["better_than_selected"]]

    return {
        "fixture_id": int(rec.fixture_id),
        "selected_insurance": pick.to_dict() if pick else None,
        "reduces_uncovered_probability": reduces,
        "incremental_uncovered_probability_mass": (
            float(pick.incremental_uncovered_probability_mass) if pick else 0.0
        ),
        "overlap_too_much": overlap_too_much,
        "primary_overlap_ratio": float(pick.primary_overlap_ratio) if pick else None,
        "residual_uncovered_mass_after": float(pick.residual_uncovered_mass_after) if pick else None,
        "would_another_market_have_been_better": bool(better),
        "better_alternatives_by_mass": better[:5],
        "compared_families": [
            "BTTS",
            "Win to Nil",
            "Over",
            "Under",
            "Winning Margin",
            "Double Chance",
            "Win & Under",
            "Win & BTTS",
        ],
        "all_alternatives_ranked": alternatives,
    }


def build_insurance_validation(
    recommendations: list[CoverageRecommendation],
    *,
    uncovered_by: dict[int, UncoveredMassReport],
    ranked_by: dict[int, list[InsuranceCandidate]],
) -> dict[str, Any]:
    fixtures = {}
    for rec in recommendations:
        fid = int(rec.fixture_id)
        fixtures[str(fid)] = validate_insurance_for_fixture(
            rec, uncovered=uncovered_by[fid], ranked=ranked_by.get(fid, [])
        )
    n = len(fixtures)
    n_reduce = sum(1 for v in fixtures.values() if v.get("reduces_uncovered_probability"))
    return {
        "research_only": True,
        "owner_only": True,
        "fixtures": fixtures,
        "summary": {
            "n_fixtures": n,
            "n_reducing_uncovered_mass": n_reduce,
            "all_selected_reduce_uncovered": n_reduce == n and n > 0,
        },
    }


def write_insurance_validation(payload: dict[str, Any], output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "insurance_validation.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)
