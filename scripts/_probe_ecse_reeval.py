#!/usr/bin/env python3
"""Quick before/after ECSE rank check for AET fixtures."""
import json, sqlite3, sys
sys.path.insert(0, ".")
from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_live.evaluator import evaluate_frozen_snapshot, rank_from_frozen_snapshot
from worldcup_predictor.research.ecse_live.store import _hydrate_snapshot

c = sqlite3.connect("data/football_intelligence.db")
c.row_factory = sqlite3.Row
resolver = FixtureOutcomeResolver(get_settings())
for fid in [1567308, 1565179]:
    snap = _hydrate_snapshot(dict(c.execute("SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? AND is_frozen=1 ORDER BY id LIMIT 1", (fid,)).fetchone()))
    old = c.execute("SELECT * FROM ecse_prediction_evaluations WHERE fixture_id=?", (fid,)).fetchone()
    outcome = resolver.resolve(fid)
    new = evaluate_frozen_snapshot(snap, outcome)
    print(fid, "old", dict(old) if old else None)
    print("  outcome", outcome.final_score, "new", new)
    fr = c.execute("SELECT home_goals,away_goals,regulation_home_goals,regulation_away_goals FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
    print("  db", dict(fr))
