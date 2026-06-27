"""Elite promotion framework — Phase 65 (recommendations only, no routing changes)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from worldcup_predictor.autonomous.store import AutonomousStore
from worldcup_predictor.config.settings import Settings, get_settings

MARKETS = (
    "1x2",
    "double_chance",
    "btts",
    "over_under_2_5",
    "correct_score",
    "goal_timing",
    "first_goal_team",
    "team_to_score_first",
    "goalscorer",
)

PromotionState = Literal[
    "BLOCKED",
    "RESEARCH_ONLY",
    "PAPER_READY",
    "MICRO_TEST_READY",
    "PRODUCTION_READY",
]

ENGINES = ("production", "elite_shadow")

GATES = {
    "PAPER_READY": {"min_evaluated": 100},
    "MICRO_TEST_READY": {"min_evaluated": 300},
    "PRODUCTION_READY": {"min_evaluated": 1000},
}

MIN_POSITIVE_ROI = 0.0
MAX_CALIBRATION_ERROR = 0.12


@dataclass
class MarketPromotionView:
    market_id: str
    production: dict[str, Any] = field(default_factory=dict)
    elite: dict[str, Any] = field(default_factory=dict)
    promotion_state: PromotionState = "BLOCKED"
    recommendation: str = "keep_production"
    blocked_reasons: list[str] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)
    evaluations_remaining: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "production": self.production,
            "elite": self.elite,
            "promotion_state": self.promotion_state,
            "recommendation": self.recommendation,
            "blocked_reasons": self.blocked_reasons,
            "missing_data": self.missing_data,
            "evaluations_remaining": self.evaluations_remaining,
        }


def _safe_prob(value: float | None) -> float | None:
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
    return p


def _brier_and_logloss(samples: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    if not samples:
        return None, None
    brier_sum = 0.0
    logloss_sum = 0.0
    n = 0
    for row in samples:
        prob = _safe_prob(row.get("model_prob"))
        outcome = row.get("outcome")
        if prob is None or outcome is None:
            continue
        y = 1.0 if outcome == "correct" else 0.0
        brier_sum += (prob - y) ** 2
        p_clip = min(max(prob, 1e-6), 1 - 1e-6)
        logloss_sum += -(y * math.log(p_clip) + (1 - y) * math.log(1 - p_clip))
        n += 1
    if n == 0:
        return None, None
    return round(brier_sum / n, 4), round(logloss_sum / n, 4)


def _roi_from_samples(samples: list[dict[str, Any]]) -> float | None:
    stakes = 0
    returns = 0.0
    for row in samples:
        odds = row.get("odds_decimal")
        if odds is None:
            continue
        try:
            o = float(odds)
        except (TypeError, ValueError):
            continue
        if o <= 1.0:
            continue
        stakes += 1
        if row.get("outcome") == "correct":
            returns += o
    if stakes == 0:
        return None
    return round((returns - stakes) / stakes, 4)


def _tier_performance(samples: list[dict[str, Any]]) -> dict[str, Any]:
    tiers: dict[str, dict[str, int]] = {}
    for row in samples:
        tier = str(row.get("tier") or "unknown")
        tiers.setdefault(tier, {"correct": 0, "wrong": 0})
        if row.get("outcome") == "correct":
            tiers[tier]["correct"] += 1
        elif row.get("outcome") == "wrong":
            tiers[tier]["wrong"] += 1
    out: dict[str, Any] = {}
    for tier, counts in tiers.items():
        ev = counts["correct"] + counts["wrong"]
        out[tier] = {
            **counts,
            "evaluated": ev,
            "winrate": round(counts["correct"] / ev, 4) if ev else None,
        }
    return out


def _load_evaluated_samples(
    store: AutonomousStore,
    *,
    engine: str,
    market_id: str,
    rolling_days: int | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT e.status, s.confidence, s.tier, s.odds_decimal
        FROM autonomous_snapshot_evaluations e
        JOIN autonomous_prediction_snapshots s ON s.id = e.snapshot_id
        WHERE e.engine = ? AND e.market_id = ?
          AND e.status IN ('correct', 'wrong')
    """
    params: list[Any] = [engine, market_id]
    if rolling_days:
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=rolling_days)).replace(tzinfo=None).isoformat()
        query += " AND e.evaluated_at >= ?"
        params.append(cutoff)
    rows = store._conn.execute(query, params).fetchall()  # noqa: SLF001
    return [
        {
            "outcome": row["status"],
            "model_prob": row["confidence"],
            "tier": row["tier"],
            "odds_decimal": row["odds_decimal"],
        }
        for row in rows
    ]


def _engine_metrics(
    store: AutonomousStore,
    *,
    engine: str,
    market_id: str,
) -> dict[str, Any]:
    agg = store.aggregate_performance(engine=engine, market_id=market_id)
    samples = _load_evaluated_samples(store, engine=engine, market_id=market_id)
    brier, logloss = _brier_and_logloss(samples)
    roi = _roi_from_samples(samples)
    winrate = agg.get("winrate")
    calibration_error = None
    if winrate is not None and samples:
        probs = [_safe_prob(s.get("model_prob")) for s in samples]
        probs = [p for p in probs if p is not None]
        if probs:
            calibration_error = round(abs(sum(probs) / len(probs) - winrate), 4)

    predictions = store._conn.execute(  # noqa: SLF001
        "SELECT COUNT(*) AS c FROM autonomous_prediction_snapshots WHERE engine = ? AND market_id = ?",
        (engine, market_id),
    ).fetchone()
    pred_count = int(predictions["c"]) if predictions else 0

    rolling: dict[str, Any] = {}
    for days in (7, 30, 90):
        rolling[f"{days}d"] = store.aggregate_performance(
            engine=engine, market_id=market_id, rolling_days=days
        )

    return {
        "engine": engine,
        "market_id": market_id,
        "predictions": pred_count,
        "evaluated": int(agg.get("evaluated") or 0),
        "pending": int(agg.get("pending") or 0),
        "winrate": winrate,
        "roi": roi,
        "brier_score": brier,
        "log_loss": logloss,
        "calibration_error": calibration_error,
        "tier_performance": _tier_performance(samples),
        "rolling": rolling,
        "certification": _legacy_cert(agg),
    }


def _legacy_cert(agg: dict[str, Any]) -> str:
    evaluated = int(agg.get("evaluated") or 0)
    winrate = agg.get("winrate")
    if evaluated < 5:
        return "BLOCKED"
    if evaluated >= 30 and winrate is not None and winrate >= 0.52:
        return "PRODUCTION_READY"
    if evaluated >= 15 and winrate is not None and winrate >= 0.48:
        return "PAPER_READY"
    return "RESEARCH_ONLY"


def _promotion_state_for_elite(
    elite: dict[str, Any],
    production: dict[str, Any],
) -> tuple[PromotionState, list[str], list[str], str]:
    reasons: list[str] = []
    missing: list[str] = []
    evaluated = int(elite.get("evaluated") or 0)

    if evaluated < GATES["PAPER_READY"]["min_evaluated"]:
        missing.append(
            f"Need {GATES['PAPER_READY']['min_evaluated'] - evaluated} more elite evaluations for PAPER_READY"
        )
        return "BLOCKED", reasons, missing, "keep_production"

    elite_wr = elite.get("winrate")
    prod_wr = production.get("winrate")
    if elite_wr is not None and prod_wr is not None and elite_wr <= prod_wr:
        reasons.append("Elite winrate must exceed production for same market")

    roi = elite.get("roi")
    if roi is not None and roi <= MIN_POSITIVE_ROI:
        reasons.append("Elite ROI must be positive when odds exist")

    cal = elite.get("calibration_error")
    if cal is not None and cal > MAX_CALIBRATION_ERROR:
        reasons.append("Calibration error too high")

    if reasons:
        return "RESEARCH_ONLY", reasons, missing, "keep_production"

    if evaluated >= GATES["PRODUCTION_READY"]["min_evaluated"]:
        return "PRODUCTION_READY", reasons, missing, "eligible_for_production_review"
    if evaluated >= GATES["MICRO_TEST_READY"]["min_evaluated"]:
        return "MICRO_TEST_READY", reasons, missing, "micro_test_elite"
    if evaluated >= GATES["PAPER_READY"]["min_evaluated"]:
        return "PAPER_READY", reasons, missing, "paper_test_elite"

    return "RESEARCH_ONLY", reasons, missing, "keep_production"


def build_promotion_status(*, settings: Settings | None = None) -> dict[str, Any]:
    from worldcup_predictor.owner.dashboard_metrics import promotion_progress_block

    settings = settings or get_settings()
    store = AutonomousStore(settings)
    markets_out: list[dict[str, Any]] = []
    total_elite_evals = 0

    for market_id in MARKETS:
        prod = _engine_metrics(store, engine="production", market_id=market_id)
        elite = _engine_metrics(store, engine="elite_shadow", market_id=market_id)
        state, reasons, missing, rec = _promotion_state_for_elite(elite, prod)
        remaining = {
            "paper_ready": max(0, GATES["PAPER_READY"]["min_evaluated"] - int(elite.get("evaluated") or 0)),
            "micro_test_ready": max(0, GATES["MICRO_TEST_READY"]["min_evaluated"] - int(elite.get("evaluated") or 0)),
            "production_ready": max(0, GATES["PRODUCTION_READY"]["min_evaluated"] - int(elite.get("evaluated") or 0)),
        }
        markets_out.append(
            MarketPromotionView(
                market_id=market_id,
                production=prod,
                elite=elite,
                promotion_state=state,
                recommendation=rec,
                blocked_reasons=reasons,
                missing_data=missing,
                evaluations_remaining=remaining,
            ).to_dict()
        )
        total_elite_evals = max(total_elite_evals, int(elite.get("evaluated") or 0))

    progress = promotion_progress_block(total_elite_evals)
    return {
        "status": "ok",
        "disclaimer": "Recommendations only — does not change public engine routing.",
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
        "gates": GATES,
        "promotion_progress": progress,
        "markets": markets_out,
        "summary": {
            "paper_ready_count": sum(1 for m in markets_out if m["promotion_state"] == "PAPER_READY"),
            "micro_test_count": sum(1 for m in markets_out if m["promotion_state"] == "MICRO_TEST_READY"),
            "production_review_count": sum(1 for m in markets_out if m["promotion_state"] == "PRODUCTION_READY"),
            "blocked_count": sum(1 for m in markets_out if m["promotion_state"] == "BLOCKED"),
        },
    }
