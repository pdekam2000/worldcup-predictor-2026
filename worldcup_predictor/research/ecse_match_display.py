"""PHASE ECSE-UI-1 — Read-only ECSE match display payload (no model changes)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.data_import.historical_csv_odds import _norm_team
from worldcup_predictor.prediction.lambda_bridge.shadow_store import ShadowStore
from worldcup_predictor.research.ecse_score_distribution import METHOD_VERSION as ECSE_DIST_VERSION

PHASE = "ECSE-UI-1"
DISPLAY_VERSION = "ECSE-UI-1-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (name,)
        ).fetchone()
    )


def confidence_tier(data_quality_score: float | None) -> str:
    q = float(data_quality_score or 0)
    if q >= 0.60:
        return "A"
    if q >= 0.40:
        return "B"
    return "C"


def resolve_registry_fixture_id(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any]:
    """Resolve production fixture_id → historical registry_fixture_id (read-only)."""
    if _table_exists(conn, "historical_provider_mapping"):
        row = conn.execute(
            """
            SELECT registry_fixture_id, confidence_score, match_method
            FROM historical_provider_mapping
            WHERE provider = 'api_football' AND provider_fixture_id = ?
            ORDER BY confidence_score DESC
            LIMIT 1
            """,
            (fixture_id,),
        ).fetchone()
        if row:
            return {
                "registry_fixture_id": int(row["registry_fixture_id"]),
                "resolve_method": "historical_provider_mapping",
                "mapping_confidence": float(row["confidence_score"]),
            }

    if _table_exists(conn, "historical_fixture_registry"):
        row = conn.execute(
            """
            SELECT registry_fixture_id FROM historical_fixture_registry
            WHERE internal_fixture_id = ?
            LIMIT 1
            """,
            (fixture_id,),
        ).fetchone()
        if row:
            return {
                "registry_fixture_id": int(row["registry_fixture_id"]),
                "resolve_method": "registry_internal_fixture_id",
                "mapping_confidence": 1.0,
            }

    fx = conn.execute(
        "SELECT home_team, away_team, kickoff_utc FROM fixtures WHERE fixture_id = ?",
        (fixture_id,),
    ).fetchone()
    if not fx or not fx["kickoff_utc"]:
        return {"registry_fixture_id": None, "resolve_method": "unresolved"}

    date_part = str(fx["kickoff_utc"])[:10]
    home_n = _norm_team(fx["home_team"])
    away_n = _norm_team(fx["away_team"])
    if not _table_exists(conn, "historical_fixture_registry"):
        return {"registry_fixture_id": None, "resolve_method": "unresolved"}
    rows = conn.execute(
        """
        SELECT registry_fixture_id FROM historical_fixture_registry
        WHERE substr(COALESCE(kickoff_utc, match_date), 1, 10) = ?
          AND home_team_normalized = ?
          AND away_team_normalized = ?
        LIMIT 3
        """,
        (date_part, home_n, away_n),
    ).fetchall()
    if len(rows) == 1:
        return {
            "registry_fixture_id": int(rows[0]["registry_fixture_id"]),
            "resolve_method": "exact_date_teams",
            "mapping_confidence": 0.88,
        }
    if len(rows) > 1:
        return {
            "registry_fixture_id": int(rows[0]["registry_fixture_id"]),
            "resolve_method": "ambiguous_date_teams",
            "mapping_confidence": 0.65,
        }
    return {"registry_fixture_id": None, "resolve_method": "unresolved"}


def _load_lambda(conn: sqlite3.Connection, registry_fixture_id: int) -> dict[str, Any] | None:
    if not _table_exists(conn, "ecse_lambda_features"):
        return None
    row = conn.execute(
        """
        SELECT lambda_home, lambda_away, lambda_total, data_quality_score,
               draw_proxy_probability, missing_draw_flag, method_version
        FROM ecse_lambda_features
        WHERE registry_fixture_id = ?
        """,
        (registry_fixture_id,),
    ).fetchone()
    if not row:
        return None
    dq = float(row["data_quality_score"])
    return {
        "lambda_home": round(float(row["lambda_home"]), 4),
        "lambda_away": round(float(row["lambda_away"]), 4),
        "lambda_total": round(float(row["lambda_total"]), 4),
        "data_quality_score": round(dq, 4),
        "confidence_tier": confidence_tier(dq),
        "draw_proxy_probability": row["draw_proxy_probability"],
        "missing_draw_flag": bool(row["missing_draw_flag"]),
        "method_version": row["method_version"],
    }


def _load_top_scores(conn: sqlite3.Connection, registry_fixture_id: int, *, limit: int = 5) -> list[dict[str, Any]]:
    if not _table_exists(conn, "ecse_score_distributions"):
        return []
    rows = conn.execute(
        """
        SELECT scoreline, probability, rank, home_goals, away_goals
        FROM ecse_score_distributions
        WHERE registry_fixture_id = ?
        ORDER BY rank
        LIMIT ?
        """,
        (registry_fixture_id, limit),
    ).fetchall()
    return [
        {
            "scoreline": r["scoreline"],
            "probability": round(float(r["probability"]), 6),
            "probability_pct": round(float(r["probability"]) * 100, 2),
            "rank": int(r["rank"]),
            "home_goals": int(r["home_goals"]),
            "away_goals": int(r["away_goals"]),
        }
        for r in rows
    ]


def _parse_correct_score_odds(payload: dict[str, Any]) -> dict[str, float]:
    """Extract scoreline -> decimal odds from odds snapshot payload."""
    out: dict[str, float] = {}
    bookmakers = payload.get("bookmakers") or payload.get("api_sports", {}).get("bookmakers") or []
    if isinstance(bookmakers, dict):
        bookmakers = [bookmakers]
    for bm in bookmakers:
        if not isinstance(bm, dict):
            continue
        for bet in bm.get("bets") or []:
            name = str(bet.get("name") or "").lower()
            if "correct score" not in name and "exact score" not in name:
                continue
            for val in bet.get("values") or []:
                label = str(val.get("value") or val.get("label") or "").strip()
                if "-" not in label:
                    continue
                try:
                    odd = float(val.get("odd") or val.get("odds") or 0)
                except (TypeError, ValueError):
                    continue
                if odd >= 1.0:
                    out[label.replace(":", "-")] = odd
    return out


def _load_market_correct_score_odds(conn: sqlite3.Connection, fixture_id: int) -> dict[str, float]:
    row = conn.execute(
        """
        SELECT payload_json FROM odds_snapshots
        WHERE fixture_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (fixture_id,),
    ).fetchone()
    if not row:
        return {}
    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        return {}
    return _parse_correct_score_odds(payload if isinstance(payload, dict) else {})


def _elite_adjustments(fixture_id: int) -> dict[str, Any] | None:
    store = ShadowStore()
    if not store.path.is_file():
        return None
    for rec in reversed(store.load_all()):
        if int(rec.get("fixture_id") or 0) != int(fixture_id):
            continue
        return {
            "source": "lambda_bridge_shadow",
            "mode": rec.get("mode"),
            "shadow_lambda_home": rec.get("shadow_lambda_home"),
            "shadow_lambda_away": rec.get("shadow_lambda_away"),
            "production_lambda_home": rec.get("production_lambda_home"),
            "production_lambda_away": rec.get("production_lambda_away"),
            "shadow_scoreline": rec.get("shadow_scoreline"),
            "production_scoreline": rec.get("production_scoreline"),
            "data_quality_scale": rec.get("data_quality_scale"),
            "global_cap_applied": rec.get("global_cap_applied"),
        }
    return None


def _best_value_score(top_prob: float | None, market_odds: float | None) -> dict[str, Any] | None:
    if top_prob is None or market_odds is None or market_odds < 1.0:
        return None
    implied = 1.0 / market_odds
    edge = top_prob - implied
    ev = top_prob * market_odds - 1.0
    return {
        "model_probability": round(top_prob, 6),
        "market_odds": round(market_odds, 3),
        "implied_probability": round(implied, 6),
        "probability_edge": round(edge, 6),
        "expected_value": round(ev, 4),
        "value_score": round(edge * 100, 2),
    }


def build_ecse_fixture_display(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any]:
    """Assemble ECSE UI payload for a production fixture (read-only)."""
    resolved = resolve_registry_fixture_id(conn, fixture_id)
    registry_id = resolved.get("registry_fixture_id")

    payload: dict[str, Any] = {
        "phase": PHASE,
        "display_version": DISPLAY_VERSION,
        "generated_at_utc": _utc_now(),
        "fixture_id": fixture_id,
        "available": False,
        "registry_fixture_id": registry_id,
        "registry_resolve": resolved,
        "distribution_method": ECSE_DIST_VERSION,
        "top_scores": [],
        "lambda": None,
        "confidence_tier": None,
        "elite_adjustments": _elite_adjustments(fixture_id),
        "best_value": None,
        "disclaimer": "Research-only ECSE independent Poisson scores. Not betting advice.",
    }

    if registry_id is None:
        payload["unavailable_reason"] = "no_registry_mapping"
        return payload

    lambdas = _load_lambda(conn, registry_id)
    scores = _load_top_scores(conn, registry_id, limit=5)
    if not scores:
        payload["unavailable_reason"] = "no_score_distribution"
        if lambdas:
            payload["lambda"] = lambdas
            payload["confidence_tier"] = lambdas.get("confidence_tier")
        return payload

    payload["available"] = True
    payload["top_scores"] = scores
    payload["lambda"] = lambdas
    if lambdas:
        payload["confidence_tier"] = lambdas.get("confidence_tier")

    top = scores[0]
    market_odds = _load_market_correct_score_odds(conn, fixture_id)
    top_odds = market_odds.get(top["scoreline"])
    payload["best_value"] = _best_value_score(float(top["probability"]), top_odds)
    if market_odds:
        payload["market_correct_score_odds_available"] = len(market_odds)

    return payload
