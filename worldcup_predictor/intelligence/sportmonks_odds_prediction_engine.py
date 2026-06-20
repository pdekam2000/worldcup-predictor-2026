"""Sportmonks odds + prediction normalization and benchmark intelligence — Phase 22C."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ConflictLevel = Literal["low", "medium", "high"]
Recommendation = Literal["support_internal", "caution", "no_bet_review"]

_HOME_LABELS = frozenset({"home", "1", "home win", "1x2 home"})
_DRAW_LABELS = frozenset({"draw", "x", "tie"})
_AWAY_LABELS = frozenset({"away", "2", "away win", "1x2 away"})
_1X2_MARKET_HINTS = frozenset({"1x2", "fulltime result", "full time result", "match winner", "3way"})


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().replace("%", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_label(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _outcome_key(label: str) -> str | None:
    key = _normalize_label(label)
    if key in _HOME_LABELS or key.startswith("home"):
        return "home"
    if key in _DRAW_LABELS or key == "draw":
        return "draw"
    if key in _AWAY_LABELS or key.startswith("away"):
        return "away"
    return None


def _implied_from_decimal(odd: float | None) -> float | None:
    if odd is None or odd <= 1.0:
        return None
    return 1.0 / odd


def _normalize_probs(probs: dict[str, float | None]) -> dict[str, float]:
    cleaned = {k: v for k, v in probs.items() if v is not None and v > 0}
    total = sum(cleaned.values())
    if total <= 0:
        return {}
    return {k: round(v / total, 4) for k, v in cleaned.items()}


def _lean_from_probs(probs: dict[str, float]) -> str:
    if not probs:
        return "draw"
    best = max(probs.items(), key=lambda x: x[1])
    return {"home": "home_win", "draw": "draw", "away": "away_win"}.get(best[0], "draw")


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_sportmonks_odds(raw_odds: Any) -> dict[str, Any]:
    """Parse Sportmonks fixture odds include — store raw + implied 1X2 consensus."""
    entries = _safe_list(raw_odds)
    if not entries:
        return {"available": False, "source": "sportmonks"}

    by_outcome: dict[str, list[float]] = {"home": [], "draw": [], "away": []}
    raw_sample: list[dict[str, Any]] = []

    for row in entries:
        if not isinstance(row, dict):
            continue
        if len(raw_sample) < 5:
            raw_sample.append(
                {
                    "bookmaker_id": row.get("bookmaker_id"),
                    "market_id": row.get("market_id"),
                    "label": row.get("label") or row.get("name"),
                    "value": row.get("value"),
                }
            )

        market_name = ""
        market = row.get("market")
        if isinstance(market, dict):
            market_name = _normalize_label(market.get("name") or market.get("developer_name"))
        market_id = row.get("market_id")
        if market_id not in (None, 1) and market_name and not any(h in market_name for h in _1X2_MARKET_HINTS):
            continue

        label = row.get("label") or row.get("name") or row.get("description")
        outcome = _outcome_key(str(label or ""))
        if outcome is None:
            continue

        decimal = _float_or_none(row.get("value"))
        if decimal is None:
            prob = _float_or_none(row.get("probability"))
            if prob is not None and prob > 1:
                prob = prob / 100.0
            if prob is not None and prob > 0:
                decimal = 1.0 / prob if prob < 1 else None
        if decimal is not None and decimal > 1.0:
            by_outcome[outcome].append(decimal)

    avg_odds: dict[str, float | None] = {}
    implied: dict[str, float | None] = {}
    for side, values in by_outcome.items():
        if values:
            avg = sum(values) / len(values)
            avg_odds[side] = round(avg, 3)
            implied[side] = _implied_from_decimal(avg)

    norm = _normalize_probs({k: v for k, v in implied.items() if v is not None})
    available = bool(norm)

    return {
        "available": available,
        "source": "sportmonks",
        "bookmaker_count": max(len(v) for v in by_outcome.values()) if available else 0,
        "average_decimal_odds": avg_odds,
        "implied_probabilities": norm,
        "market_favorite": _lean_from_probs(norm) if norm else None,
        "raw_odds_sample": raw_sample,
        "disclaimer": "Sportmonks odds are supplemental — API-Football odds remain primary.",
    }


def normalize_sportmonks_predictions(raw_predictions: Any, metadata: Any = None) -> dict[str, Any]:
    """Parse Sportmonks prediction model output — benchmark only."""
    entries = _safe_list(raw_predictions)
    pred_block: dict[str, Any] = {}
    row: dict[str, Any] = {}
    if entries and isinstance(entries[0], dict):
        row = entries[0]
        nested = row.get("predictions")
        if isinstance(nested, dict):
            pred_block = nested
        elif isinstance(nested, list) and nested and isinstance(nested[0], dict):
            pred_block = nested[0]
        else:
            pred_block = row

    home = _float_or_none(pred_block.get("home") or pred_block.get("home_win"))
    draw = _float_or_none(pred_block.get("draw"))
    away = _float_or_none(pred_block.get("away") or pred_block.get("away_win"))

    if home is not None and home > 1:
        home /= 100.0
    if draw is not None and draw > 1:
        draw /= 100.0
    if away is not None and away > 1:
        away /= 100.0

    probs = _normalize_probs({"home": home, "draw": draw, "away": away})

    expected_home = _float_or_none(pred_block.get("goals_home") or pred_block.get("home_goals"))
    expected_away = _float_or_none(pred_block.get("goals_away") or pred_block.get("away_goals"))
    scores = pred_block.get("scores")
    if isinstance(scores, dict):
        if expected_home is None:
            expected_home = _float_or_none(scores.get("home"))
        if expected_away is None:
            expected_away = _float_or_none(scores.get("away"))
    expected_score: str | None = None
    if expected_home is not None and expected_away is not None:
        expected_score = f"{expected_home:.1f}-{expected_away:.1f}"

    meta = metadata if isinstance(metadata, dict) else {}
    eligible = meta.get("predictions") if isinstance(meta.get("predictions"), bool) else None
    confidence_raw = _float_or_none(pred_block.get("confidence") or row.get("confidence") if entries else None)
    if confidence_raw is not None and confidence_raw <= 1:
        confidence_raw *= 100.0

    if not confidence_raw and probs:
        confidence_raw = max(probs.values()) * 100.0

    return {
        "available": bool(probs),
        "source": "sportmonks",
        "home_probability": probs.get("home"),
        "draw_probability": probs.get("draw"),
        "away_probability": probs.get("away"),
        "probabilities": probs,
        "lean": _lean_from_probs(probs) if probs else None,
        "expected_score": expected_score,
        "confidence": round(confidence_raw, 1) if confidence_raw is not None else None,
        "metadata_eligible": eligible,
        "raw_prediction_sample": pred_block if pred_block else None,
        "disclaimer": "Sportmonks prediction is external benchmark only — never overrides internal model.",
    }


def parse_odds_predictions_from_fixture(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract odds + predictions blocks from a Sportmonks fixture object."""
    odds = normalize_sportmonks_odds(raw.get("odds"))
    predictions = normalize_sportmonks_predictions(raw.get("predictions"), raw.get("metadata"))
    return {
        "odds": odds,
        "predictions": predictions,
        "raw_odds_present": bool(_safe_list(raw.get("odds"))),
        "raw_predictions_present": bool(_safe_list(raw.get("predictions"))),
    }


def build_internal_reference(signals: dict[str, Any]) -> dict[str, Any]:
    """Build internal lean from existing specialist signals (no Sportmonks)."""
    mc = signals.get("market_consensus_agent")
    if mc is not None and getattr(mc, "is_usable", False):
        block = mc.signals if hasattr(mc, "signals") else mc
        probs = {
            "home": block.get("home_implied_probability"),
            "draw": block.get("draw_implied_probability"),
            "away": block.get("away_implied_probability"),
        }
        norm = _normalize_probs(probs)
        if norm:
            return {
                "available": True,
                "source": "market_consensus_agent",
                "probabilities": norm,
                "lean": _lean_from_probs(norm),
            }

    om = signals.get("odds_market_agent")
    if om is not None and getattr(om, "is_usable", False):
        block = om.signals if hasattr(om, "signals") else om
        implied = block.get("implied_probabilities") or {}
        if isinstance(implied, dict) and implied:
            norm = _normalize_probs(
                {
                    "home": _float_or_none(implied.get("home")),
                    "draw": _float_or_none(implied.get("draw")),
                    "away": _float_or_none(implied.get("away")),
                }
            )
            if norm:
                return {
                    "available": True,
                    "source": "odds_market_agent",
                    "probabilities": norm,
                    "lean": _lean_from_probs(norm),
                }

    form = signals.get("team_form_agent")
    if form is not None and getattr(form, "is_usable", False):
        block = form.signals if hasattr(form, "signals") else form
        home_f = _float_or_none(block.get("form_score_home")) or 50.0
        away_f = _float_or_none(block.get("form_score_away")) or 50.0
        diff = home_f - away_f
        if abs(diff) < 5:
            probs = {"home": 0.33, "draw": 0.34, "away": 0.33}
            lean = "draw"
        elif diff > 0:
            boost = min(diff / 100.0, 0.25)
            probs = _normalize_probs({"home": 0.33 + boost, "draw": 0.33, "away": 0.33 - boost})
            lean = _lean_from_probs(probs)
        else:
            boost = min(abs(diff) / 100.0, 0.25)
            probs = _normalize_probs({"home": 0.33 - boost, "draw": 0.33, "away": 0.33 + boost})
            lean = _lean_from_probs(probs)
        return {
            "available": True,
            "source": "team_form_agent",
            "probabilities": probs,
            "lean": lean,
        }

    return {"available": False, "source": "none", "probabilities": {}, "lean": "draw"}


def _probability_l1_distance(a: dict[str, float], b: dict[str, float]) -> float:
    keys = ("home", "draw", "away")
    return sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys)


def _consensus_with_internal(
    sm_probs: dict[str, float],
    internal: dict[str, Any],
) -> float:
    if not sm_probs or not internal.get("available"):
        return 50.0
    internal_probs = internal.get("probabilities") or {}
    if not internal_probs:
        sm_lean = _lean_from_probs(sm_probs)
        internal_lean = internal.get("lean", "draw")
        if sm_lean == internal_lean:
            return 85.0
        if sm_lean == "draw" or internal_lean == "draw":
            return 55.0
        if {sm_lean, internal_lean} == {"home_win", "away_win"}:
            return 5.0
        return 35.0
    dist = _probability_l1_distance(sm_probs, internal_probs)
    return round(max(0.0, min(100.0, (1.0 - dist / 2.0) * 100.0)), 1)


def _conflict_level(
    disagreement: float,
    *,
    odds_market_disagreement: float | None = None,
) -> ConflictLevel:
    score = disagreement
    if odds_market_disagreement is not None:
        score = max(score, odds_market_disagreement)
    if score >= 0.45:
        return "high"
    if score >= 0.22:
        return "medium"
    return "low"


def _recommendation(
    conflict: ConflictLevel,
    consensus: float,
) -> Recommendation:
    if conflict == "high" or consensus < 35.0:
        return "no_bet_review"
    if conflict == "medium" or consensus < 60.0:
        return "caution"
    return "support_internal"


def _odds_vs_api_disagreement(
    sm_odds: dict[str, Any],
    api_probs: dict[str, float],
) -> float | None:
    sm_probs = sm_odds.get("implied_probabilities") or {}
    if not sm_probs or not api_probs:
        return None
    return round(_probability_l1_distance(sm_probs, api_probs) / 2.0, 3)


@dataclass
class SportmonksPredictionIntelligenceResult:
    sportmonks_home_probability: float | None = None
    sportmonks_draw_probability: float | None = None
    sportmonks_away_probability: float | None = None
    sportmonks_expected_score: str | None = None
    sportmonks_confidence: float | None = None
    disagreement_vs_internal: float | None = None
    consensus_with_internal: float = 50.0
    conflict_level: ConflictLevel = "low"
    recommendation: Recommendation = "caution"
    sportmonks_odds_available: bool = False
    sportmonks_prediction_available: bool = False
    odds_vs_api_football_disagreement: float | None = None
    internal_reference_source: str = "none"
    internal_lean: str = "draw"
    sportmonks_lean: str | None = None
    raw_odds: dict[str, Any] = field(default_factory=dict)
    raw_predictions: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    version: str = "22c"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_sportmonks_prediction_intelligence(
    *,
    odds_prediction_block: dict[str, Any] | None,
    specialist_signals: dict[str, Any],
) -> SportmonksPredictionIntelligenceResult:
    """Build benchmark intelligence — no prediction overrides."""
    block = odds_prediction_block or {}
    sm_odds = block.get("odds") or {}
    sm_pred = block.get("predictions") or {}

    internal = build_internal_reference(specialist_signals)
    internal_probs = internal.get("probabilities") or {}

    sm_probs = sm_pred.get("probabilities") or {}
    if not sm_probs and sm_odds.get("implied_probabilities"):
        sm_probs = sm_odds["implied_probabilities"]

    disagreement: float | None = None
    if sm_probs and internal_probs:
        disagreement = round(_probability_l1_distance(sm_probs, internal_probs) / 2.0, 3)
    elif sm_probs and internal.get("available"):
        sm_lean = sm_pred.get("lean") or _lean_from_probs(sm_probs)
        internal_lean = internal.get("lean", "draw")
        if sm_lean == internal_lean:
            disagreement = 0.05
        elif sm_lean == "draw" or internal_lean == "draw":
            disagreement = 0.25
        elif {sm_lean, internal_lean} == {"home_win", "away_win"}:
            disagreement = 0.55
        else:
            disagreement = 0.35

    odds_vs_api = _odds_vs_api_disagreement(sm_odds, internal_probs) if internal_probs else None

    consensus = _consensus_with_internal(sm_probs, internal) if sm_probs else 50.0
    conflict = _conflict_level(
        disagreement or 0.0,
        odds_market_disagreement=odds_vs_api,
    )
    rec = _recommendation(conflict, consensus)

    notes: list[str] = []
    if not sm_odds.get("available") and not sm_pred.get("available"):
        notes.append("Sportmonks odds and prediction unavailable in fixture payload.")
    if sm_odds.get("available"):
        notes.append("Sportmonks odds loaded as supplemental market reference.")
    if sm_pred.get("available"):
        notes.append("Sportmonks prediction model used as external benchmark only.")
    if odds_vs_api is not None and odds_vs_api >= 0.22:
        notes.append(
            f"Sportmonks odds diverge from API-Football consensus ({odds_vs_api:.0%}) — analysis only."
        )
    if conflict == "high":
        notes.append("High conflict between Sportmonks benchmark and internal lean — review only.")

    return SportmonksPredictionIntelligenceResult(
        sportmonks_home_probability=sm_pred.get("home_probability"),
        sportmonks_draw_probability=sm_pred.get("draw_probability"),
        sportmonks_away_probability=sm_pred.get("away_probability"),
        sportmonks_expected_score=sm_pred.get("expected_score"),
        sportmonks_confidence=sm_pred.get("confidence"),
        disagreement_vs_internal=disagreement,
        consensus_with_internal=consensus,
        conflict_level=conflict,
        recommendation=rec,
        sportmonks_odds_available=bool(sm_odds.get("available")),
        sportmonks_prediction_available=bool(sm_pred.get("available")),
        odds_vs_api_football_disagreement=odds_vs_api,
        internal_reference_source=str(internal.get("source") or "none"),
        internal_lean=str(internal.get("lean") or "draw"),
        sportmonks_lean=sm_pred.get("lean") or sm_odds.get("market_favorite"),
        raw_odds=sm_odds,
        raw_predictions=sm_pred,
        notes=notes,
    )
