"""Goalscorer intelligence shadow layer — per-fixture structured output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.goalscorer_intelligence.confidence_engine import assign_confidence_tiers, confidence_summary
from worldcup_predictor.egie.goalscorer_intelligence.feature_pipeline import (
    attach_ml_scores,
    enrich_intelligence_features,
    load_bridge_dataset,
)
from worldcup_predictor.egie.goalscorer_intelligence.models import FixtureIntelligence
from worldcup_predictor.egie.goalscorer_intelligence.ranking_engine import (
    add_ranks,
    identify_surprise_candidates,
    identify_value_picks,
    team_scoring_threats,
    top_n_players,
)

BRIDGE_FIXTURES = Path("artifacts/phase54o_goalscorer_bridge/fixture_bridge.json")


def _load_fixture_meta() -> dict[int, dict[str, Any]]:
    if not BRIDGE_FIXTURES.is_file():
        return {}
    bridges = json.loads(BRIDGE_FIXTURES.read_text(encoding="utf-8"))
    out: dict[int, dict[str, Any]] = {}
    for b in bridges:
        sm = b.get("sportmonks_fixture_id")
        if sm:
            out[int(sm)] = b
    return out


def build_fixture_intelligence(df: pd.DataFrame, *, meta: dict[int, dict[str, Any]] | None = None) -> list[FixtureIntelligence]:
    meta = meta or _load_fixture_meta()
    fixtures: list[FixtureIntelligence] = []

    for fid, grp in df.groupby("sportmonks_fixture_id"):
        fid_int = int(fid)
        m = meta.get(fid_int) or {}
        fixtures.append(
            FixtureIntelligence(
                sportmonks_fixture_id=fid_int,
                api_football_fixture_id=m.get("api_football_fixture_id"),
                home_team=m.get("home_team"),
                away_team=m.get("away_team"),
                match_date=m.get("match_date"),
                top_anytime_scorers=top_n_players(grp, "composite_scorer_score"),
                top_first_goalscorers=top_n_players(grp, "composite_first_goal_score"),
                top_surprise_candidates=identify_surprise_candidates(grp),
                top_value_candidates=identify_value_picks(grp),
                top_team_scoring_threats=team_scoring_threats(grp),
                confidence_summary=confidence_summary(grp),
            )
        )
    return fixtures


def generate_intelligence(
    dataset_path: Path | str | None = None,
) -> tuple[pd.DataFrame, list[FixtureIntelligence]]:
    """Full pipeline: load v2 → ML scores → features → ranks → confidence → fixture intel."""
    raw = load_bridge_dataset(dataset_path)
    scored = attach_ml_scores(raw)
    enriched = enrich_intelligence_features(scored)
    ranked = add_ranks(enriched)
    final = assign_confidence_tiers(ranked)
    intel = build_fixture_intelligence(final)
    return final, intel
