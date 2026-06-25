"""Part A — Elite Orchestrator shadow runtime engine (cache-first, no production)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.provider_features.odds_snapshot_parser import (
    normalize_snapshot_odds_lines,
    parse_implied_1x2,
)
from worldcup_predictor.egie.uefa_club.odds_intelligence import parse_uefa_odds_deep
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache
from worldcup_predictor.elite_orchestrator.confidence import compute_tier, model_agreement_score
from worldcup_predictor.elite_orchestrator.shadow_config import MARKETS, MODEL_VERSION
from worldcup_predictor.elite_orchestrator.shadow_store import flatten_prediction_record
from worldcup_predictor.elite_self_learning.adaptive_weights import DEFAULT_WEIGHTS
from worldcup_predictor.elite_self_learning.weight_simulation.replay import build_contributions, fuse_pick, load_gs_proxy

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "football_intelligence.db"
GOALSCORER_PATH = ROOT / "artifacts" / "phase54q_goalscorer_generalization" / "goalscorer_dataset_v3.parquet"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_odds_snapshot(fixture_id: int) -> dict[str, Any] | None:
    if not DB_PATH.is_file():
        return None
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT payload_json FROM odds_snapshots WHERE fixture_id=? ORDER BY rowid DESC LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    conn.close()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return None


def _load_sportmonks_cache(sportmonks_fixture_id: int | None) -> dict[str, Any] | None:
    if not sportmonks_fixture_id:
        return None
    from worldcup_predictor.config.settings import get_settings

    path = cache_path(get_settings(), int(sportmonks_fixture_id))
    return load_cache(path)


def _load_enrichment_payload(fixture_id: int, sportmonks_fixture_id: int | None) -> dict[str, Any] | None:
    if not DB_PATH.is_file():
        return None
    conn = sqlite3.connect(DB_PATH)
    row = None
    if sportmonks_fixture_id:
        row = conn.execute(
            "SELECT raw_json FROM sportmonks_fixture_enrichment WHERE sportmonks_fixture_id=? AND status='ok' ORDER BY id DESC LIMIT 1",
            (int(sportmonks_fixture_id),),
        ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT raw_json FROM sportmonks_fixture_enrichment WHERE fixture_id_api_football=? AND status='ok' ORDER BY id DESC LIMIT 1",
            (int(fixture_id),),
        ).fetchone()
    conn.close()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return None


def _goalscorer_top3(sportmonks_fixture_id: int | None) -> list[str]:
    if not sportmonks_fixture_id or not GOALSCORER_PATH.is_file():
        return []
    try:
        import pandas as pd

        gs = pd.read_parquet(
            GOALSCORER_PATH,
            columns=["sportmonks_fixture_id", "player_name", "goals_per_90", "starter_probability", "combined_score"],
        )
        sub = gs[gs["sportmonks_fixture_id"] == int(sportmonks_fixture_id)].copy()
        if sub.empty:
            return []
        sub["score"] = sub.get("combined_score", sub["goals_per_90"]).fillna(0) * sub["starter_probability"].fillna(0)
        sub = sub.sort_values("score", ascending=False)
        return sub["player_name"].head(3).astype(str).tolist()
    except Exception:
        return []


def _contrib_dict(cid: str, weight: float, prediction: Any, confidence: float, evidence: dict | None = None) -> dict:
    return {
        "component_id": cid,
        "weight": round(weight, 4),
        "prediction": prediction,
        "confidence": round(confidence, 4),
        "evidence": evidence or {},
    }


def generate_shadow_prediction(fixture: dict[str, Any]) -> dict[str, Any]:
    """Build EliteShadowPrediction bundle for one fixture using cache-first data."""
    fixture_id = int(fixture["fixture_id"])
    sm_id = fixture.get("sportmonks_fixture_id")
    sm_id_int = int(sm_id) if sm_id else None

    cache = _load_sportmonks_cache(sm_id_int)
    enrichment = _load_enrichment_payload(fixture_id, sm_id_int)
    odds_payload = _load_odds_snapshot(fixture_id)

    odds_deep: dict[str, Any] = {}
    if cache:
        odds_deep = parse_uefa_odds_deep(cache)
    elif enrichment:
        odds_deep = parse_uefa_odds_deep(enrichment)

    implied_1x2: dict[str, float] = {}
    if odds_payload:
        lines = normalize_snapshot_odds_lines(odds_payload, fixture_id=fixture_id)
        implied_1x2 = parse_implied_1x2(lines)

    if not implied_1x2 and odds_deep.get("consensus_implied_home") is not None:
        implied_1x2 = {
            "home": float(odds_deep.get("consensus_implied_home") or 0),
            "draw": float(odds_deep.get("consensus_implied_draw") or 0),
            "away": float(odds_deep.get("consensus_implied_away") or 0),
        }

    # Proxy row for fusion helpers
    home_rate = float(implied_1x2.get("home") or 0.33)
    away_rate = float(implied_1x2.get("away") or 0.33)

    class _Row:
        sportmonks_fixture_id = sm_id_int or fixture_id
        home_goal_rate_proxy = home_rate
        away_goal_rate_proxy = away_rate
        label_first_goal_team = "home"

    gs_proxy = load_gs_proxy()
    contributions_raw, base_conf, tier_letter = build_contributions(_Row(), gs_proxy)
    weights = DEFAULT_WEIGHTS["first_goal_team"]

    component_preds = {
        c["component_id"]: c.get("prediction")
        for c in contributions_raw
    }
    agreement = model_agreement_score({k: v for k, v in component_preds.items() if v})

    fgt_pick, fgt_prob, _ = fuse_pick(contributions_raw, weights)
    fgt_tier = compute_tier(fgt_prob)
    fts_home = odds_deep.get("first_team_score_home")
    fts_away = odds_deep.get("first_team_score_away")

    top3 = _goalscorer_top3(sm_id_int)
    gs_conf = 0.45 + min(0.25, len(top3) * 0.05)

    mw_pick = max(implied_1x2, key=implied_1x2.get) if implied_1x2 else fgt_pick
    mw_conf = max(implied_1x2.values()) if implied_1x2 else fgt_prob

    fusion = {
        "model_agreement": agreement,
        "market_agreement": round(max(implied_1x2.values()) if implied_1x2 else 0.5, 4),
        "mbi_prior_applied": False,
        "mbi_blend_weight": 0.0,
        "odds_confidence": round(mw_conf, 4),
        "data_quality": round(0.4 + 0.1 * bool(odds_payload) + 0.2 * bool(cache or enrichment) + 0.1 * bool(top3), 4),
        "overall_tier": fgt_tier,
    }

    markets: dict[str, dict[str, Any]] = {
        "first_goal_team": {
            "prediction": fgt_pick,
            "confidence": fgt_prob,
            "tier": fgt_tier,
            "evidence": {
                "fts_implied_home": fts_home,
                "fts_implied_away": fts_away,
                "feature_group": "baseline_goalscorer",
            },
            "reasoning": [
                f"Weighted fusion pick: {fgt_pick}",
                f"Model agreement: {agreement:.2f}",
            ],
            "component_contributions": [
                _contrib_dict(c["component_id"], weights.get(c["component_id"], 0.1), c["prediction"], float(c["confidence"]))
                for c in contributions_raw
            ],
        },
        "team_to_score_first": {
            "prediction": fgt_pick,
            "confidence": fgt_prob,
            "tier": fgt_tier,
            "evidence": {"alias": "first_goal_team"},
            "reasoning": ["Mirrors first_goal_team fusion path"],
            "component_contributions": [],
        },
        "1x2": {
            "prediction": implied_1x2 if implied_1x2 else {"home": 0.33, "draw": 0.34, "away": 0.33},
            "confidence": mw_conf,
            "tier": compute_tier(mw_conf),
            "evidence": {"source": "odds_snapshots" if odds_payload else "sportmonks_odds"},
            "reasoning": ["Odds-implied probabilities from cache"],
            "component_contributions": [
                _contrib_dict("odds_intelligence", 0.6, mw_pick, mw_conf),
                _contrib_dict("market_behavior_intelligence", 0.1, None, 0.45),
            ],
        },
        "anytime_goalscorer": {
            "prediction": top3,
            "confidence": gs_conf,
            "tier": compute_tier(gs_conf),
            "evidence": {"players_ranked": len(top3), "has_lineup_data": bool(top3)},
            "reasoning": ["Top-3 from goalscorer dataset v3 composite" if top3 else "No player rows for fixture"],
            "component_contributions": [
                _contrib_dict("goalscorer_intelligence", 0.55, top3, gs_conf),
                _contrib_dict("lineup_intelligence", 0.15, None, 0.5),
                _contrib_dict("player_form_store", 0.20, None, 0.5),
            ],
        },
        "first_goalscorer": {
            "prediction": top3[:3],
            "confidence": round(gs_conf * 0.7, 4),
            "tier": "C",
            "evidence": {"research_tier_cap": True},
            "reasoning": ["First goalscorer inherits anytime ranking — tier capped"],
            "component_contributions": [
                _contrib_dict("goalscorer_intelligence", 0.85, top3[:1] if top3 else None, gs_conf * 0.7),
            ],
        },
        "goal_timing": {
            "prediction": {"range": "16-30", "minute_estimate": 25},
            "confidence": 0.35,
            "tier": "C",
            "evidence": {"mode": "egie_proxy_default", "experimental": True},
            "reasoning": ["Goal timing uses EGIE default range proxy until live EGIE shadow wired"],
            "component_contributions": [
                _contrib_dict("egie_historical_baseline", 0.9, {"range": "16-30"}, 0.35),
                _contrib_dict("hybrid_confidence_engine", 0.1, None, 0.35),
            ],
        },
    }

    return {
        "fixture_id": fixture_id,
        "sportmonks_fixture_id": sm_id_int,
        "competition_key": fixture.get("competition_key"),
        "league_id": fixture.get("league_id"),
        "home_team": fixture.get("home_team"),
        "away_team": fixture.get("away_team"),
        "generated_at": _utc_now(),
        "kickoff_time": fixture.get("kickoff_utc"),
        "markets": markets,
        "fusion": fusion,
        "confidence_tiers": {"overall": fusion["overall_tier"], "by_market": {m: markets[m]["tier"] for m in markets}},
        "model_versions": {
            "elite_orchestrator": MODEL_VERSION,
            "fgt_v2_group": "baseline_goalscorer",
            "goalscorer_intel": "54Q_v3",
            "hybrid_confidence": "52D_shadow",
        },
        "meta": {
            "phase": "58C",
            "source": fixture.get("source"),
            "has_odds_snapshot": bool(odds_payload),
            "has_sportmonks_cache": bool(cache or enrichment),
            "is_shadow": True,
            "is_user_visible": False,
        },
    }


def run_shadow_for_fixtures(fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate flat JSONL rows (one per market) for all fixtures."""
    rows: list[dict[str, Any]] = []
    for fx in fixtures:
        bundle = generate_shadow_prediction(fx)
        for market_id in MARKETS:
            block = bundle["markets"].get(market_id)
            if not block:
                continue
            rows.append(flatten_prediction_record(bundle, market_id=market_id, market_block=block))
    return rows
