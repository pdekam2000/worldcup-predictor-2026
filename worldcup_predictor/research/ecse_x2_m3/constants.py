"""PHASE ECSE-X2-M3 — Champion/Challenger shadow validation constants."""

from __future__ import annotations

import math

PHASE = "ECSE-X2-M3"
METHOD_VERSION = "ECSE-X2-M3-v1"
EQUATION_NAME = "log_home_prob_phi"
EQUATION_LABEL = "log(home_prob) / log(1.618)"
PHI = 1.618
LOG_PHI = math.log(PHI)

SHADOW_ARTIFACT = "artifacts/ecse_x2_m3_champion_challenger_shadow.jsonl"
TRAIN_FRACTION = 0.70
NUM_TEMPORAL_FOLDS = 5
TOP_N_SHADOW = 10
TOP_N_STORE = 15

MAX_LOG_LOSS_WORSEN = 0.01
MIN_FOLD_SAMPLE = 2_000
MIN_FOLDS_IMPROVED_TOP3 = 3
MAX_RANK_VOLATILITY = 2.5
MIN_ELIGIBLE_SAMPLE = 5_000
