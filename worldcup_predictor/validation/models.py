"""Phase 26 — real-world validation models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ContributionVerdict = Literal["helped", "neutral", "harmful", "unknown"]
SignalUsefulness = Literal["helped", "neutral", "harmful", "unknown"]


@dataclass
class PromotionTrackSnapshot:
    """Per-promotion tracking (24A / 24B / 24C xG / 24C SM)."""

    promotion_key: str
    signal_available: bool = False
    confidence: float = 0.0
    delta: float = 0.0
    agreement: float | None = None
    disagreement: float | None = None
    active: bool = False
    reason: str = ""
    mode: str = "shadow"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IntelligenceSnapshots:
    lineup_snapshot: dict[str, Any] = field(default_factory=dict)
    expected_lineup_snapshot: dict[str, Any] = field(default_factory=dict)
    tournament_context_snapshot: dict[str, Any] = field(default_factory=dict)
    xg_snapshot: dict[str, Any] = field(default_factory=dict)
    sportmonks_prediction_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RealWorldValidationRecord:
    fixture_id: int
    match_date: str
    prediction_timestamp: str
    match_name: str
    competition_key: str = "world_cup_2026"
    predicted_1x2: str = ""
    predicted_over_under: str = ""
    confidence: float = 0.0
    baseline_confidence: float = 0.0
    no_bet_flag: bool = False
    data_quality_score: float = 0.0
    actual_1x2: str | None = None
    actual_over_under: str | None = None
    settled: bool = False
    settled_at: str | None = None
    one_x_two_correct: bool | None = None
    over_under_correct: bool | None = None
    confidence_bucket: str = ""
    confidence_calibration_ok: bool | None = None
    snapshots: IntelligenceSnapshots = field(default_factory=IntelligenceSnapshots)
    promotions: list[PromotionTrackSnapshot] = field(default_factory=list)
    promotion_deltas: dict[str, float] = field(default_factory=dict)
    shadow_signals: dict[str, Any] = field(default_factory=dict)
    signal_usefulness: dict[str, str] = field(default_factory=dict)
    version: str = "26"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["snapshots"] = self.snapshots.to_dict()
        payload["promotions"] = [p.to_dict() for p in self.promotions]
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RealWorldValidationRecord:
        snaps_raw = data.get("snapshots") or {}
        snaps = IntelligenceSnapshots(
            lineup_snapshot=dict(snaps_raw.get("lineup_snapshot") or {}),
            expected_lineup_snapshot=dict(snaps_raw.get("expected_lineup_snapshot") or {}),
            tournament_context_snapshot=dict(snaps_raw.get("tournament_context_snapshot") or {}),
            xg_snapshot=dict(snaps_raw.get("xg_snapshot") or {}),
            sportmonks_prediction_snapshot=dict(snaps_raw.get("sportmonks_prediction_snapshot") or {}),
        )
        promos = [
            PromotionTrackSnapshot(**p) if isinstance(p, dict) else p
            for p in (data.get("promotions") or [])
        ]
        return cls(
            fixture_id=int(data["fixture_id"]),
            match_date=str(data.get("match_date") or ""),
            prediction_timestamp=str(data.get("prediction_timestamp") or ""),
            match_name=str(data.get("match_name") or ""),
            competition_key=str(data.get("competition_key") or "world_cup_2026"),
            predicted_1x2=str(data.get("predicted_1x2") or ""),
            predicted_over_under=str(data.get("predicted_over_under") or ""),
            confidence=float(data.get("confidence") or 0),
            baseline_confidence=float(data.get("baseline_confidence") or 0),
            no_bet_flag=bool(data.get("no_bet_flag")),
            data_quality_score=float(data.get("data_quality_score") or 0),
            actual_1x2=data.get("actual_1x2"),
            actual_over_under=data.get("actual_over_under"),
            settled=bool(data.get("settled")),
            settled_at=data.get("settled_at"),
            one_x_two_correct=data.get("one_x_two_correct"),
            over_under_correct=data.get("over_under_correct"),
            confidence_bucket=str(data.get("confidence_bucket") or ""),
            confidence_calibration_ok=data.get("confidence_calibration_ok"),
            snapshots=snaps,
            promotions=promos,
            promotion_deltas=dict(data.get("promotion_deltas") or {}),
            shadow_signals=dict(data.get("shadow_signals") or {}),
            signal_usefulness=dict(data.get("signal_usefulness") or {}),
            version=str(data.get("version") or "26"),
        )


@dataclass
class PromotionContributionStats:
    promotion_key: str
    total: int = 0
    helped: int = 0
    neutral: int = 0
    harmful: int = 0
    unknown: int = 0
    signal_available_rate: float = 0.0
    avg_delta: float = 0.0
    avg_disagreement: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorldCupReadinessScore:
    score: float
    data_quality: float
    lineup_coverage: float
    context_coverage: float
    xg_coverage: float
    prediction_quality: float
    sample_size: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
