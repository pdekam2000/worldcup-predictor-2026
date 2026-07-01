"""PHASE ECSE-X2-M2 — Market algebra equation miner constants."""

from __future__ import annotations

PHASE = "ECSE-X2-M2"
METHOD_VERSION = "ECSE-X2-M2-v1"

MIN_TRAIN_SAMPLE = 5_000
MIN_TEST_SAMPLE = 3_000
MAX_LOG_LOSS_WORSEN = 0.005
MIN_LEAGUES_IMPROVED = 3
MIN_LEAGUE_SAMPLE = 800
TRAIN_FRACTION = 0.70
NUM_QUANTILES = 5
REORDER_POWER = 1.12
TOP_SCORES_STORED = 15
PHI_TARGETS = (0.618, 1.618, 2.618)

SCORE_CLUSTERS: dict[str, frozenset[str]] = {
    "low_total": frozenset({"0-0", "1-0", "0-1", "1-1"}),
    "home_win": frozenset({"1-0", "2-0", "2-1", "3-0", "3-1", "4-0"}),
    "away_win": frozenset({"0-1", "0-2", "1-2", "0-3", "1-3", "0-4"}),
    "drawish": frozenset({"0-0", "1-1", "2-2"}),
    "high_scoring": frozenset({"2-2", "3-1", "1-3", "3-2", "2-3", "3-3", "4-1", "1-4"}),
}
