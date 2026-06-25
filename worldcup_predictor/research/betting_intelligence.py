"""Betting intelligence engine — Phase 65 (research only, no betting advice)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from worldcup_predictor.autonomous.store import AutonomousStore
from worldcup_predictor.config.settings import Settings, get_settings

DISCLAIMER = "Research only — not betting advice."

BetLabel = Literal[
    "VALUE_CANDIDATE",
    "WATCH_ONLY",
    "NO_BET",
    "INSUFFICIENT_ODDS",
    "INSUFFICIENT_MODEL_CONFIDENCE",
    "DATA_QUALITY_BLOCKED",
]

DEFAULT_KELLY_FRACTION = 0.25
DEFAULT_MAX_STAKE_RISK = 0.02
MIN_EDGE_FOR_VALUE = 0.03
MIN_MODEL_CONFIDENCE = 0.52
MIN_ODDS = 1.05


@dataclass
class BettingIntelligenceConfig:
    kelly_fraction: float = DEFAULT_KELLY_FRACTION
    max_stake_risk: float = DEFAULT_MAX_STAKE_RISK
    min_edge_for_value: float = MIN_EDGE_FOR_VALUE
    min_model_confidence: float = MIN_MODEL_CONFIDENCE


@dataclass
class BettingRow:
    snapshot_id: int
    fixture_id: int
    market_id: str
    engine: str
    home_team: str | None
    away_team: str | None
    kickoff_utc: str | None
    model_probability: float | None
    odds_decimal: float | None
    implied_probability: float | None
    edge: float | None
    ev: float | None
    fair_odds: float | None
    kelly_full: float | None
    kelly_capped: float | None
    suggested_stake_risk: float | None
    confidence_tier: str | None
    label: BetLabel
    data_quality_warning: str | None = None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "fixture_id": self.fixture_id,
            "fixture": f"{self.home_team or '?'} vs {self.away_team or '?'}",
            "market_id": self.market_id,
            "engine": self.engine,
            "kickoff_utc": self.kickoff_utc,
            "model_probability": self.model_probability,
            "odds_decimal": self.odds_decimal,
            "implied_probability": self.implied_probability,
            "edge": self.edge,
            "ev": self.ev,
            "fair_odds": self.fair_odds,
            "kelly_full": self.kelly_full,
            "kelly_capped": self.kelly_capped,
            "suggested_stake_risk": self.suggested_stake_risk,
            "confidence_tier": self.confidence_tier,
            "label": self.label,
            "data_quality_warning": self.data_quality_warning,
            "reasons": self.reasons,
            "disclaimer": DISCLAIMER,
        }


def _normalize_prob(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        p = float(value)
    except (TypeError, ValueError):
        return None
    if p > 1.0:
        p = p / 100.0
    if p <= 0 or p >= 1:
        return None
    return round(p, 4)


def _implied_from_odds(odds: float | None) -> float | None:
    if odds is None:
        return None
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o < MIN_ODDS:
        return None
    return round(1.0 / o, 4)


def _compute_kelly(model_p: float, odds: float) -> float | None:
    if odds <= 1.0:
        return None
    num = model_p * odds - 1.0
    den = odds - 1.0
    if den <= 0:
        return None
    return max(0.0, num / den)


def analyze_snapshot_row(
    snap: dict[str, Any],
    *,
    config: BettingIntelligenceConfig | None = None,
) -> BettingRow:
    config = config or BettingIntelligenceConfig()
    reasons: list[str] = []
    dq_warning: str | None = None

    model_p = _normalize_prob(snap.get("confidence"))
    odds = snap.get("odds_decimal")
    try:
        odds_f = float(odds) if odds is not None else None
    except (TypeError, ValueError):
        odds_f = None

    implied = _implied_from_odds(odds_f)
    edge = None
    ev = None
    fair = None
    kelly_full = None
    kelly_capped = None
    stake_risk = None
    label: BetLabel = "NO_BET"

    if snap.get("source") == "elite_shadow" and snap.get("is_user_visible") in (0, False):
        pass  # owner research only — still analyze for owner dashboard

    if odds_f is None or implied is None:
        label = "INSUFFICIENT_ODDS"
        reasons.append("Missing or invalid bookmaker odds")
    elif model_p is None:
        label = "INSUFFICIENT_MODEL_CONFIDENCE"
        reasons.append("Model probability unavailable")
    elif model_p < config.min_model_confidence:
        label = "INSUFFICIENT_MODEL_CONFIDENCE"
        reasons.append(f"Model confidence below {config.min_model_confidence}")
    else:
        edge = round(model_p - implied, 4)
        ev = round(model_p * (odds_f - 1.0) - (1.0 - model_p), 4)
        fair = round(1.0 / model_p, 3)
        kelly_full = _compute_kelly(model_p, odds_f)
        if kelly_full is not None:
            kelly_capped = round(min(kelly_full * config.kelly_fraction, config.max_stake_risk), 4)
            stake_risk = kelly_capped
        if edge >= config.min_edge_for_value and ev is not None and ev > 0:
            label = "VALUE_CANDIDATE"
            reasons.append("Positive EV above minimum edge threshold")
        elif edge is not None and edge > 0:
            label = "WATCH_ONLY"
            reasons.append("Positive edge but below value threshold or EV marginal")
        else:
            label = "NO_BET"
            reasons.append("No positive edge")

    tier = snap.get("tier")
    if tier and str(tier).lower() in {"low", "blocked", "skip"}:
        label = "DATA_QUALITY_BLOCKED"
        dq_warning = f"Low confidence tier: {tier}"
        reasons.append(dq_warning)

    return BettingRow(
        snapshot_id=int(snap.get("id") or 0),
        fixture_id=int(snap.get("fixture_id") or 0),
        market_id=str(snap.get("market_id") or ""),
        engine=str(snap.get("engine") or ""),
        home_team=snap.get("home_team"),
        away_team=snap.get("away_team"),
        kickoff_utc=snap.get("kickoff_utc"),
        model_probability=model_p,
        odds_decimal=odds_f,
        implied_probability=implied,
        edge=edge,
        ev=ev,
        fair_odds=fair,
        kelly_full=round(kelly_full, 4) if kelly_full is not None else None,
        kelly_capped=kelly_capped,
        suggested_stake_risk=stake_risk,
        confidence_tier=tier,
        label=label,
        data_quality_warning=dq_warning,
        reasons=reasons,
    )


def analyze_sample_odds(
    *,
    model_probability: float,
    odds_decimal: float,
    config: BettingIntelligenceConfig | None = None,
) -> dict[str, Any]:
    """Public helper for validation / unit-style checks."""
    snap = {
        "id": 0,
        "fixture_id": 0,
        "market_id": "1x2",
        "engine": "production",
        "confidence": model_probability,
        "odds_decimal": odds_decimal,
        "tier": "medium",
    }
    return analyze_snapshot_row(snap, config=config).to_dict()


def build_betting_intelligence(
    *,
    settings: Settings | None = None,
    limit: int = 200,
    config: BettingIntelligenceConfig | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    store = AutonomousStore(settings)
    snaps = store.list_snapshots(limit=limit)
    rows = [analyze_snapshot_row(s, config=config).to_dict() for s in snaps]

    value_candidates = [r for r in rows if r["label"] == "VALUE_CANDIDATE"]
    no_bet = [r for r in rows if r["label"] in ("NO_BET", "INSUFFICIENT_ODDS", "INSUFFICIENT_MODEL_CONFIDENCE", "DATA_QUALITY_BLOCKED")]
    watch = [r for r in rows if r["label"] == "WATCH_ONLY"]

    ev_buckets: dict[str, int] = {"negative": 0, "zero": 0, "small_positive": 0, "strong_positive": 0, "unknown": 0}
    for r in rows:
        ev = r.get("ev")
        if ev is None:
            ev_buckets["unknown"] += 1
        elif ev < 0:
            ev_buckets["negative"] += 1
        elif ev == 0:
            ev_buckets["zero"] += 1
        elif ev < 0.05:
            ev_buckets["small_positive"] += 1
        else:
            ev_buckets["strong_positive"] += 1

    return {
        "status": "ok",
        "disclaimer": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
        "config": {
            "kelly_fraction": (config or BettingIntelligenceConfig()).kelly_fraction,
            "max_stake_risk": (config or BettingIntelligenceConfig()).max_stake_risk,
        },
        "summary": {
            "total_analyzed": len(rows),
            "value_candidates": len(value_candidates),
            "watch_only": len(watch),
            "no_bet": len(no_bet),
            "ev_buckets": ev_buckets,
        },
        "value_candidates": value_candidates[:50],
        "watch_only": watch[:30],
        "no_bet": no_bet[:50],
        "rows": rows,
    }
