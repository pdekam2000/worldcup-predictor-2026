"""Types for ephemeral canonical research predictions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ResearchContext:
    experiment_id: str
    experiment_date: str
    snapshot_class: str
    audit_id: str
    scope: str = "owner"
    caller: str = "ecse_timing_experiment"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EphemeralCanonicalPrediction:
    fixture_id: int
    execution_mode: str
    complete: bool
    odds: dict[str, Any]
    wde: dict[str, Any]
    btts: dict[str, Any]
    ou25: dict[str, Any]
    ecse: dict[str, Any]
    consensus: str | None
    no_bet: bool | None
    no_bet_diagnostics: dict[str, Any]
    pick_tier: str | None
    model_version: str | None
    model_config_hash: str | None
    odds_content_hash: str | None
    research_output_hash: str | None
    warnings: list[str] = field(default_factory=list)
    quality_status: str | None = None
    canonical_writes_attempted: int = 0
    canonical_writes_completed: int = 0
    freeze_created: bool = False
    freeze_updated: bool = False
    wsp_written: bool = False
    ecse_canonical_written: bool = False
    research_only: bool = True
    canonical: bool = False
    final_decision_authority: bool = False
    raw_wde_payload: dict[str, Any] | None = None
    raw_ecse_prediction: dict[str, Any] | None = None
    confidence_lineage: dict[str, Any] = field(default_factory=dict)
    research_integrity_warnings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
