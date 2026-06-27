"""Phase 62 — World Cup EGIE data expansion configuration."""

from __future__ import annotations

from dataclasses import dataclass

WORLD_CUP_COMPETITION_KEY = "world_cup_2026"
API_FOOTBALL_LEAGUE_ID = 1
SPORTMONKS_LEAGUE_ID = 732

# Target historical seasons (API-Football season year) — Phase 62B extended
WORLD_CUP_SEASONS: tuple[int, ...] = (1998, 2002, 2006, 2010, 2014, 2018, 2022, 2026)

# Finals-only seasons for EGIE backtest pool (excludes qualifiers)
WORLD_CUP_FINALS_SEASONS: tuple[int, ...] = WORLD_CUP_SEASONS

COMPETITION_TYPE_FINALS = "world_cup_finals"
COMPETITION_TYPE_QUALIFIER = "world_cup_qualifier"
COMPETITION_TYPE_FRIENDLY = "friendly"
COMPETITION_TYPE_OTHER = "other"

MAPPING_AUDIT_OUTPUT = "data/validation/phase62b_mapping_audit.json"
PROGRESS_CHECKPOINT_PATH = "data/validation/phase62b_progress.json"
WC_MAPPING_TABLE = "wc_fixture_mapping"

# Coverage targets (Part F)
TARGET_FIXTURES = 500
TARGET_XG_COVERAGE = 0.70
TARGET_LINEUP_COVERAGE = 0.80
TARGET_ODDS_COVERAGE = 0.80
TARGET_GOAL_EVENT_COVERAGE = 0.90

RAW_CACHE_DIR = "data/egie/world_cup/raw"
SURVIVAL_OUTPUT = "data/egie/world_cup/survival_dataset.parquet"
TEAM_PROFILES_OUTPUT = "data/egie/world_cup/team_timing_profiles.json"
CONFEDERATION_PROFILES_OUTPUT = "data/egie/world_cup/confederation_timing_profiles.json"


@dataclass(frozen=True)
class WorldCupSeasonSpec:
    season: int
    label: str
    sportmonks_season_label: str | None = None


WORLD_CUP_SEASON_SPECS: tuple[WorldCupSeasonSpec, ...] = tuple(
    WorldCupSeasonSpec(s, f"FIFA World Cup {s}", str(s) if s >= 2018 else None)
    for s in WORLD_CUP_SEASONS
)
