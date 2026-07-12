"""Leakage classification for provider features."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class LeakageClass(str, Enum):
    SAFE_PREMATCH = "SAFE_PREMATCH"
    SAFE_IF_SNAPSHOT_TIMESTAMP_VALID = "SAFE_IF_SNAPSHOT_TIMESTAMP_VALID"
    LIVE_ONLY = "LIVE_ONLY"
    POST_MATCH_ONLY = "POST_MATCH_ONLY"
    LEAKAGE_RISK = "LEAKAGE_RISK"
    UNUSABLE_FOR_BACKTEST = "UNUSABLE_FOR_BACKTEST"


@dataclass(frozen=True)
class FeatureLeakageSpec:
    feature: str
    provider: str
    leakage_class: LeakageClass
    cutoff_rule: str
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "provider": self.provider,
            "leakage_class": self.leakage_class.value,
            "cutoff_rule": self.cutoff_rule,
            "notes": self.notes,
        }


FEATURE_LEAKAGE_REGISTRY: tuple[FeatureLeakageSpec, ...] = (
    FeatureLeakageSpec(
        "odds_home/draw/away",
        "api-football|oddalerts|sportmonks|the-odds-api",
        LeakageClass.SAFE_IF_SNAPSHOT_TIMESTAMP_VALID,
        "snapshot_at <= prediction_cutoff < kickoff",
        "Canonical odds_snapshots; closing odds after kickoff excluded.",
    ),
    FeatureLeakageSpec(
        "implied_prob_*",
        "derived_odds",
        LeakageClass.SAFE_IF_SNAPSHOT_TIMESTAMP_VALID,
        "same as odds snapshot",
        "Derived from pre-match 1X2/O-U/BTTS odds only.",
    ),
    FeatureLeakageSpec(
        "expectedGoalsHome/Away (CSV)",
        "external_historical_csv",
        LeakageClass.POST_MATCH_ONLY,
        "realized match xG — unavailable pre-kickoff",
        "EXCLUDED from primary shadow fusion; diagnostic upper-bound only.",
    ),
    FeatureLeakageSpec(
        "xg_snapshots",
        "sportmonks",
        LeakageClass.SAFE_IF_SNAPSHOT_TIMESTAMP_VALID,
        "snapshot_at <= prediction_cutoff",
        "Sparse coverage; validate timestamp per row.",
    ),
    FeatureLeakageSpec(
        "home_form/away_form",
        "api-football",
        LeakageClass.SAFE_PREMATCH,
        "form computed from matches before cutoff",
        "Requires explicit form-as-of date in enrichment.",
    ),
    FeatureLeakageSpec(
        "fixture_enrichment.statistics_json",
        "api-football",
        LeakageClass.POST_MATCH_ONLY,
        "match statistics after FT",
        "Shots/possession/pressure from completed match — leakage.",
    ),
    FeatureLeakageSpec(
        "lineups_json",
        "api-football",
        LeakageClass.SAFE_IF_SNAPSHOT_TIMESTAMP_VALID,
        "lineup snapshot <= 4h pre-kickoff typical",
        "Lineup release timing must be validated per fixture.",
    ),
    FeatureLeakageSpec(
        "injuries",
        "api-football",
        LeakageClass.SAFE_IF_SNAPSHOT_TIMESTAMP_VALID,
        "injury list as-of prediction cutoff",
        "Injury updates after cutoff are leakage.",
    ),
    FeatureLeakageSpec(
        "standings/motivation",
        "api-football|sportmonks",
        LeakageClass.SAFE_PREMATCH,
        "standings before kickoff round",
        "Must use standings as-of prior matchday.",
    ),
    FeatureLeakageSpec(
        "pressure_index",
        "sportmonks",
        LeakageClass.LIVE_ONLY,
        "in-match pressure feed",
        "Not for pre-match WDE/ECSE backtest.",
    ),
    FeatureLeakageSpec(
        "oddalerts_probability_market_rows",
        "oddalerts_csv",
        LeakageClass.SAFE_IF_SNAPSHOT_TIMESTAMP_VALID,
        "CSV row timestamp / fixture pre-kickoff",
        "Primary OddAlerts path is Gmail CSV import.",
    ),
    FeatureLeakageSpec(
        "provider_prediction_model",
        "api-football|sportmonks|oddalerts",
        LeakageClass.SAFE_IF_SNAPSHOT_TIMESTAMP_VALID,
        "provider prediction fetched pre-kickoff",
        "Reference only; not official production pick.",
    ),
    FeatureLeakageSpec(
        "closing_odds",
        "any",
        LeakageClass.LEAKAGE_RISK,
        "closing captured at/after kickoff",
        "Never use for pre-match backtest.",
    ),
)


def safe_for_primary_fusion(leakage_class: LeakageClass) -> bool:
    return leakage_class in {
        LeakageClass.SAFE_PREMATCH,
        LeakageClass.SAFE_IF_SNAPSHOT_TIMESTAMP_VALID,
    }


def registry_dict() -> list[dict[str, Any]]:
    return [s.to_dict() for s in FEATURE_LEAKAGE_REGISTRY]
