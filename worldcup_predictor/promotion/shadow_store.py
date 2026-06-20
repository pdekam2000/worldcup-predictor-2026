"""Shadow store for expected lineup promotion (Phase 24A)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SHADOW_PATH = Path("data/shadow/expected_lineup_promotion_shadow.jsonl")
DEFAULT_CONTEXT_SHADOW_PATH = Path("data/shadow/tournament_context_promotion_shadow.jsonl")
DEFAULT_XG_SHADOW_PATH = Path("data/shadow/xg_promotion_shadow.jsonl")
DEFAULT_SPORTMONKS_SHADOW_PATH = Path("data/shadow/sportmonks_prediction_promotion_shadow.jsonl")


@dataclass
class ExpectedLineupPromotionShadowRecord:
    fixture_id: int
    timestamp: str
    mode: str
    config_version: str
    baseline_lineup_score: float
    promoted_lineup_score: float
    lineup_delta_score: float
    confidence_delta: float
    lineup_promotion_active: bool
    lineup_promotion_reason: str
    applied: bool
    gate_passed: bool
    expected_vs_confirmed_history: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "config_version": self.config_version,
            "baseline_lineup_score": self.baseline_lineup_score,
            "promoted_lineup_score": self.promoted_lineup_score,
            "lineup_delta_score": self.lineup_delta_score,
            "confidence_delta": self.confidence_delta,
            "lineup_promotion_active": self.lineup_promotion_active,
            "lineup_promotion_reason": self.lineup_promotion_reason,
            "applied": self.applied,
            "gate_passed": self.gate_passed,
            "expected_vs_confirmed_history": self.expected_vs_confirmed_history,
        }


class ExpectedLineupPromotionShadowStore:
    def __init__(self, path: Path | str = DEFAULT_SHADOW_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: ExpectedLineupPromotionShadowRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def load_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows


@dataclass
class TournamentContextPromotionShadowRecord:
    fixture_id: int
    timestamp: str
    mode: str
    config_version: str
    baseline_motivation_score: float
    promoted_motivation_score: float
    context_delta_score: float
    context_delta_edge: float
    confidence_delta: float
    context_promotion_active: bool
    context_promotion_reason: str
    must_win_influence: float
    rotation_context_influence: float
    draw_acceptability_influence: float
    tactics_over_trace_delta: float
    tactics_trace_notes: str
    applied: bool
    gate_passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "config_version": self.config_version,
            "baseline_motivation_score": self.baseline_motivation_score,
            "promoted_motivation_score": self.promoted_motivation_score,
            "context_delta_score": self.context_delta_score,
            "context_delta_edge": self.context_delta_edge,
            "confidence_delta": self.confidence_delta,
            "context_promotion_active": self.context_promotion_active,
            "context_promotion_reason": self.context_promotion_reason,
            "must_win_influence": self.must_win_influence,
            "rotation_context_influence": self.rotation_context_influence,
            "draw_acceptability_influence": self.draw_acceptability_influence,
            "tactics_over_trace_delta": self.tactics_over_trace_delta,
            "tactics_trace_notes": self.tactics_trace_notes,
            "applied": self.applied,
            "gate_passed": self.gate_passed,
        }


class TournamentContextPromotionShadowStore:
    def __init__(self, path: Path | str = DEFAULT_CONTEXT_SHADOW_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: TournamentContextPromotionShadowRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def load_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows


@dataclass
class XGPromotionShadowRecord:
    fixture_id: int
    timestamp: str
    mode: str
    config_version: str
    baseline_tactics_score: float
    promoted_tactics_score: float
    xg_delta_score: float
    xg_delta_over: float
    xg_promotion_active: bool
    xg_promotion_reason: str
    applied: bool
    gate_passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "config_version": self.config_version,
            "baseline_tactics_score": self.baseline_tactics_score,
            "promoted_tactics_score": self.promoted_tactics_score,
            "xg_delta_score": self.xg_delta_score,
            "xg_delta_over": self.xg_delta_over,
            "xg_promotion_active": self.xg_promotion_active,
            "xg_promotion_reason": self.xg_promotion_reason,
            "applied": self.applied,
            "gate_passed": self.gate_passed,
        }


class XGPromotionShadowStore:
    def __init__(self, path: Path | str = DEFAULT_XG_SHADOW_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: XGPromotionShadowRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def load_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows


@dataclass
class SportmonksPredictionPromotionShadowRecord:
    fixture_id: int
    timestamp: str
    mode: str
    config_version: str
    sportmonks_confidence_delta: float
    sportmonks_disagreement_signal: str
    sportmonks_promotion_active: bool
    sportmonks_promotion_reason: str
    no_bet_review_trace: bool
    internal_lean: str
    sportmonks_lean: str
    conflict_level: str
    applied: bool
    gate_passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "config_version": self.config_version,
            "sportmonks_confidence_delta": self.sportmonks_confidence_delta,
            "sportmonks_disagreement_signal": self.sportmonks_disagreement_signal,
            "sportmonks_promotion_active": self.sportmonks_promotion_active,
            "sportmonks_promotion_reason": self.sportmonks_promotion_reason,
            "no_bet_review_trace": self.no_bet_review_trace,
            "internal_lean": self.internal_lean,
            "sportmonks_lean": self.sportmonks_lean,
            "conflict_level": self.conflict_level,
            "applied": self.applied,
            "gate_passed": self.gate_passed,
        }


class SportmonksPredictionPromotionShadowStore:
    def __init__(self, path: Path | str = DEFAULT_SPORTMONKS_SHADOW_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: SportmonksPredictionPromotionShadowRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def load_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows
