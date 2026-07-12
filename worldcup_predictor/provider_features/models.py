"""Prematch feature snapshot models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PrematchFeatureSnapshot:
    fixture_id: int
    competition_key: str
    provider: str
    feature_family: str
    feature_name: str
    feature_value: Any
    feature_available_at_utc: str
    fetched_at_utc: str
    prediction_cutoff_utc: str
    kickoff_utc: str
    source_endpoint: str
    leakage_status: str
    tier: str | None = None
    provider_fixture_id: int | None = None
    feature_version: str = "prematch_v1"
    source_version: str | None = None
    mapping_confidence: float | None = None
    data_quality: str = "unknown"
    completeness_mask: dict[str, int] = field(default_factory=dict)
    payload_hash: str | None = None
    extra_values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "competition_key": self.competition_key,
            "tier": self.tier,
            "provider": self.provider,
            "provider_fixture_id": self.provider_fixture_id,
            "feature_family": self.feature_family,
            "feature_name": self.feature_name,
            "feature_value": self.feature_value,
            "feature_available_at_utc": self.feature_available_at_utc,
            "fetched_at_utc": self.fetched_at_utc,
            "prediction_cutoff_utc": self.prediction_cutoff_utc,
            "kickoff_utc": self.kickoff_utc,
            "source_endpoint": self.source_endpoint,
            "source_version": self.source_version,
            "feature_version": self.feature_version,
            "leakage_status": self.leakage_status,
            "mapping_confidence": self.mapping_confidence,
            "data_quality": self.data_quality,
            "completeness_mask": self.completeness_mask,
            "payload_hash": self.payload_hash,
            "extra_values": self.extra_values,
        }
