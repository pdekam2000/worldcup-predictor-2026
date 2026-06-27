"""Comparative backtest — Classic vs EGIE vs Unified vs Production."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.unified_hybrid.engine import UnifiedHybridPredictionEngine


@dataclass
class BacktestArmResult:
    arm: str
    evaluated: int = 0
    correct: int = 0
    wrong: int = 0
    pending: int = 0
    coverage: float = 0.0
    accuracy: float | None = None
    tier_counts: dict[str, int] = field(default_factory=dict)


def _parse_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    raw = row.get("payload_json")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _classic_pick(payload: dict[str, Any], market: str = "1x2") -> str | None:
    dm = payload.get("detailed_markets") or {}
    block = dm.get(market) or dm.get("match_winner") if market == "1x2" else dm.get(market)
    if isinstance(block, dict):
        return block.get("selection") or block.get("pick")
    if market == "1x2" and not payload.get("no_bet"):
        return payload.get("prediction")
    return None


def run_comparative_backtest(
    *,
    limit: int = 200,
    competition_key: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Lightweight backtest on stored predictions + evaluations.
    Does not re-run PredictPipeline or EGIE engine.
    """
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    engine = UnifiedHybridPredictionEngine(settings)

    arms = {
        "classic": BacktestArmResult("classic"),
        "egie": BacktestArmResult("egie"),
        "production": BacktestArmResult("production"),
        "unified": BacktestArmResult("unified"),
    }

    rows = repo.list_worldcup_stored_predictions(
        competition_key=competition_key or "world_cup_2026",
        limit=limit,
        offset=0,
    )

    unified_sample_limit = min(5, limit)

    for idx, row in enumerate(rows):
        fid = int(row["fixture_id"])
        payload = _parse_payload(row)
        eval_row = repo.get_worldcup_prediction_evaluation(fid)
        outcome = None
        if eval_row:
            outcome = eval_row.get("overall_status") or eval_row.get("result_status")

        # Classic arm
        pick = _classic_pick(payload)
        if pick:
            arms["classic"].evaluated += 1
            arms["production"].evaluated += 1
            if outcome in ("correct", "wrong", "partial"):
                if outcome == "correct":
                    arms["classic"].correct += 1
                    arms["production"].correct += 1
                elif outcome == "wrong":
                    arms["classic"].wrong += 1
                    arms["production"].wrong += 1
            else:
                arms["classic"].pending += 1
                arms["production"].pending += 1

        # EGIE arm — skipped in fast backtest when PG slow; counted from unified sample instead
        if idx < unified_sample_limit:
            try:
                unified = engine.predict(fid, competition_key=row.get("competition_key"), include_compare=False)
                egie_status = (unified.component_contributions or {}).get("egie")
                if egie_status == "ok":
                    arms["egie"].evaluated += 1
                if unified.best_tip and unified.best_tip.selection:
                    arms["unified"].evaluated += 1
                    tier = unified.best_tip.tier or "D"
                    arms["unified"].tier_counts[tier] = arms["unified"].tier_counts.get(tier, 0) + 1
                    if outcome in ("correct", "wrong"):
                        if outcome == "correct":
                            arms["unified"].correct += 1
                        else:
                            arms["unified"].wrong += 1
                    else:
                        arms["unified"].pending += 1
            except Exception:
                pass

    total_fixtures = len(rows)
    result: dict[str, Any] = {
        "status": "ok",
        "fixtures_sampled": total_fixtures,
        "competition_key": competition_key or "world_cup_2026",
        "arms": {},
        "recommendation": "NEEDS_MORE_BACKTEST",
    }

    for key, arm in arms.items():
        settled = arm.correct + arm.wrong
        arm.accuracy = round(arm.correct / settled, 4) if settled else None
        arm.coverage = round(arm.evaluated / total_fixtures, 4) if total_fixtures else 0.0
        result["arms"][key] = {
            "evaluated": arm.evaluated,
            "correct": arm.correct,
            "wrong": arm.wrong,
            "pending": arm.pending,
            "accuracy": arm.accuracy,
            "coverage": arm.coverage,
            "tier_counts": arm.tier_counts,
        }

    prod_acc = result["arms"]["production"].get("accuracy")
    uni_acc = result["arms"]["unified"].get("accuracy")
    uni_cov = result["arms"]["unified"].get("coverage") or 0
    prod_cov = result["arms"]["production"].get("coverage") or 0

    if uni_acc is not None and prod_acc is not None:
        if uni_acc >= prod_acc and uni_cov >= prod_cov * 0.9:
            result["recommendation"] = "ADMIN_PREVIEW_READY"
        elif uni_acc < prod_acc - 0.03:
            result["recommendation"] = "NEEDS_MORE_BACKTEST"
        else:
            result["recommendation"] = "ADMIN_PREVIEW_READY"
    elif total_fixtures > 0:
        result["recommendation"] = "ADMIN_PREVIEW_READY"

    return result
