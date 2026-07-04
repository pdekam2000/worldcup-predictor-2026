"""PHASE ECSE-UI-1 / OWNER-PREDICTIONS-UI-2 — Read-only ECSE match display (no ranking changes)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.data_import.historical_csv_odds import _norm_team
from worldcup_predictor.prediction.lambda_bridge.shadow_store import ShadowStore
from worldcup_predictor.odds.freshness_policy import (
    classify_odds_freshness,
    is_low_priority_match,
)
from worldcup_predictor.research.ecse_rerank.features import (
    extract_wde_markets,
    is_clean_sheet,
    is_knockout_fixture,
    total_goals,
)
from worldcup_predictor.research.ecse_score_distribution import METHOD_VERSION as ECSE_DIST_VERSION

PHASE = "OWNER-PREDICTIONS-UI-2"
DISPLAY_VERSION = "ECSE-UI-2-v1"
END_RESULT_DISCLAIMER = (
    "Exact score is high variance. These are the model's top ranked score candidates, "
    "not a guaranteed final result."
)
SHADOW_PREVIEW_LABEL = "Shadow advisory only — not production prediction."


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


def _load_fixture_row(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, status, round_name, competition_key
        FROM fixtures WHERE fixture_id = ?
        """,
        (fixture_id,),
    ).fetchone()
    return dict(row) if row else None


def _load_ecse_snapshot_meta(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any]:
    if not _table_exists(conn, "ecse_prediction_snapshots"):
        return {}
    row = conn.execute(
        """
        SELECT generated_at, prediction_source, model_version, top_1_score,
               top_3_scores_json, top_5_scores_json, top_10_scorelines_json
        FROM ecse_prediction_snapshots
        WHERE fixture_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (fixture_id,),
    ).fetchone()
    if not row:
        return {}
    return {
        "generated_at": row["generated_at"],
        "cache_source": row["prediction_source"],
        "prediction_engine_version": row["model_version"],
        "top_1_score": row["top_1_score"],
    }


def _load_wde_markets(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any]:
    if not _table_exists(conn, "worldcup_stored_predictions"):
        return {}
    row = conn.execute(
        "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id = ? LIMIT 1",
        (fixture_id,),
    ).fetchone()
    if not row or not row["payload_json"]:
        return {}
    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        return {}
    return extract_wde_markets(payload)


def _build_consistency_notes(
    top1: str | None,
    wde: dict[str, Any],
) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    if not top1:
        return notes
    btts = wde.get("pick_btts")
    ou = str(wde.get("pick_ou25") or "").lower()
    tg = total_goals(top1) or 0
    if btts == "yes":
        aligned = not is_clean_sheet(top1)
        notes.append(
            {
                "key": "btts",
                "label": "BTTS aligned" if aligned else "BTTS not aligned",
                "status": "aligned" if aligned else "misaligned",
            }
        )
    if "over" in ou:
        aligned = tg > 2
        notes.append(
            {
                "key": "over_under",
                "label": "O/U 2.5 aligned" if aligned else "O/U 2.5 not aligned",
                "status": "aligned" if aligned else "misaligned",
            }
        )
    elif "under" in ou:
        aligned = tg <= 2
        notes.append(
            {
                "key": "over_under",
                "label": "O/U 2.5 aligned" if aligned else "O/U 2.5 not aligned",
                "status": "aligned" if aligned else "misaligned",
            }
        )
    if is_clean_sheet(top1) and btts == "yes":
        notes.append({"key": "clean_sheet", "label": "Clean-sheet Top 1 vs BTTS Yes", "status": "warning"})
    return notes


def _load_odds_freshness_for_fixture(
    conn: sqlite3.Connection,
    fixture_id: int,
    fixture_row: dict[str, Any] | None,
    prediction_generated_at: str | None,
) -> dict[str, Any]:
    odds_snap_at = None
    odds_source = None
    if _table_exists(conn, "odds_snapshots"):
        o = conn.execute(
            "SELECT snapshot_at, payload_json FROM odds_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
            (fixture_id,),
        ).fetchone()
        if o:
            odds_snap_at = o["snapshot_at"]
            try:
                payload = json.loads(o["payload_json"])
                odds_source = payload.get("source_provider") or payload.get("source") or "odds_snapshots"
            except (json.JSONDecodeError, TypeError):
                odds_source = "odds_snapshots"
    knockout = is_knockout_fixture(fixture_row or {})
    low_pri = is_low_priority_match(kickoff_utc=(fixture_row or {}).get("kickoff_utc"))
    cls = classify_odds_freshness(
        odds_snapshot_at=odds_snap_at,
        reference_at=prediction_generated_at,
        knockout=knockout,
        low_priority=low_pri,
        odds_source=odds_source,
        has_odds=bool(odds_snap_at),
    )
    freshness = cls.to_dict()
    freshness["prediction_generated_at"] = prediction_generated_at
    flag = freshness.get("freshness_flag")
    if freshness.get("stale_odds") or flag in ("ODDS_FRESHNESS_UNKNOWN", "ODDS_MISSING", "STALE_ODDS"):
        freshness["recommendation_flag"] = "REQUIRES_FRESH_ODDS"
    else:
        freshness["recommendation_flag"] = "FRESH_ODDS_OK"
    return freshness


def _artifact_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_shadow_preview(fixture_id: int) -> dict[str, Any] | None:
    """Read shadow re-rank artifact if present — advisory only, no inference."""
    jsonl = _artifact_root() / "artifacts" / "ecse_rerank_1_shadow_results.jsonl"
    if not jsonl.is_file():
        return None
    try:
        with jsonl.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if int(row.get("fixture_id") or 0) != int(fixture_id):
                    continue
                shadow = row.get("shadow") or {}
                inner = shadow.get("shadow") or {}
                return {
                    "label": SHADOW_PREVIEW_LABEL,
                    "shadow_only": True,
                    "PUBLIC_PUBLISH": False,
                    "baseline_top_1": row.get("baseline_top1"),
                    "shadow_top_1": inner.get("top_1"),
                    "shadow_top_3": inner.get("top_3") or [],
                    "shadow_top_5": inner.get("top_5") or [],
                    "rank_changed": shadow.get("rank_changed"),
                    "consistency_notes": shadow.get("consistency_notes") or [],
                    "recommendation_flag": inner.get("recommendation_flag"),
                }
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return None


def _viewer_flags(viewer: Any | None) -> dict[str, bool]:
    role = str(getattr(viewer, "role", "") or "guest").lower()
    is_owner = role == "owner"
    is_admin = role in ("admin", "super_admin", "owner")
    is_pro = role in ("pro", "premium") or is_admin or is_owner
    return {
        "is_authenticated": viewer is not None,
        "can_view_top5": is_pro or is_admin or is_owner,
        "can_view_owner_metadata": is_admin or is_owner,
        "can_view_shadow_preview": is_admin or is_owner,
    }


def build_ecse_fixture_display(
    conn: sqlite3.Connection,
    fixture_id: int,
    *,
    viewer: Any | None = None,
) -> dict[str, Any]:
    """Assemble ECSE UI payload for a production fixture (read-only)."""
    resolved = resolve_registry_fixture_id(conn, fixture_id)
    registry_id = resolved.get("registry_fixture_id")
    fixture_row = _load_fixture_row(conn, fixture_id)
    snapshot_meta = _load_ecse_snapshot_meta(conn, fixture_id)
    access = _viewer_flags(viewer)

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
        "top_3": [],
        "top_5": [],
        "end_result_title": "End Result Candidates",
        "end_result_disclaimer": END_RESULT_DISCLAIMER,
        "lambda": None,
        "confidence_tier": None,
        "elite_adjustments": _elite_adjustments(fixture_id),
        "best_value": None,
        "disclaimer": "Research-only ECSE independent Poisson scores. Not betting advice.",
        "odds_freshness": None,
        "access": {
            "can_view_top5": access["can_view_top5"],
            "can_view_owner_metadata": access["can_view_owner_metadata"],
            "can_view_shadow_preview": access["can_view_shadow_preview"],
        },
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
    payload["top_3"] = scores[:3]
    payload["top_5"] = scores[:5] if access["can_view_top5"] else []
    payload["lambda"] = lambdas
    if lambdas:
        payload["confidence_tier"] = lambdas.get("confidence_tier")

    top = scores[0]
    market_odds = _load_market_correct_score_odds(conn, fixture_id)
    top_odds = market_odds.get(top["scoreline"])
    payload["best_value"] = _best_value_score(float(top["probability"]), top_odds)
    if market_odds:
        payload["market_correct_score_odds_available"] = len(market_odds)

    pred_at = snapshot_meta.get("generated_at")
    freshness = _load_odds_freshness_for_fixture(conn, fixture_id, fixture_row, pred_at)
    if access["can_view_owner_metadata"] or freshness.get("freshness_flag") != "ODDS_FRESHNESS_UNKNOWN":
        payload["odds_freshness"] = freshness
    elif not access["is_authenticated"]:
        payload["odds_freshness"] = None

    wde = _load_wde_markets(conn, fixture_id)
    top1_line = top.get("scoreline")
    if access["can_view_top5"]:
        payload["consistency_notes"] = _build_consistency_notes(top1_line, wde)

    if access["can_view_owner_metadata"]:
        payload["engine_meta"] = {
            "generated_at": pred_at or payload["generated_at_utc"],
            "cache_source": snapshot_meta.get("cache_source"),
            "prediction_engine_version": snapshot_meta.get("prediction_engine_version"),
        }
        if access["can_view_shadow_preview"]:
            preview = _load_shadow_preview(fixture_id)
            if preview:
                payload["shadow_preview"] = preview

    return payload
