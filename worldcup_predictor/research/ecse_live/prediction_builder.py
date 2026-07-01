"""PHASE ECSE-LIVE-1 — Build ECSE live prediction payload (research only, no WDE)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.egie.provider_features.odds_snapshot_parser import (
    normalize_snapshot_odds_lines,
)
from worldcup_predictor.research.ecse_lambda_extraction import (
    METHOD_VERSION as LAMBDA_METHOD_VERSION,
    extract_lambdas,
)
from worldcup_predictor.research.ecse_match_display import (
    _load_lambda,
    _load_top_scores,
    resolve_registry_fixture_id,
)
from worldcup_predictor.research.ecse_score_distribution import (
    METHOD_VERSION as DIST_METHOD_VERSION,
    generate_score_distribution,
)

PHASE = "ECSE-LIVE-1"
MODEL_VERSION = f"ECSE-LIVE-1|{LAMBDA_METHOD_VERSION}|{DIST_METHOD_VERSION}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (name,)
        ).fetchone()
    )


def _pick_odd(lines: list, market_filter, selection_filter) -> float | None:
    for line in lines:
        if market_filter(line.market_name, line.selection) and selection_filter(line.selection):
            return float(line.odd)
    return None


def _is_ou_line(name: str, selection: str, line: str) -> bool:
    n = name.lower()
    if "over/under" not in n and "goals over" not in n:
        return False
    return line in selection.lower()


def build_odds_feature_row(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    """Map latest odds snapshot into ECSE training row shape."""
    if not _table_exists(conn, "odds_snapshots"):
        return None
    row = conn.execute(
        """
        SELECT payload_json FROM odds_snapshots
        WHERE fixture_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        return None

    lines = normalize_snapshot_odds_lines(payload, fixture_id=fixture_id)
    if not lines:
        return None

    def mw(name: str, _sel: str) -> bool:
        n = name.lower()
        return n in {"match winner", "1x2", "match result", "home/draw/away"}

    def mw_sel(sel: str, key: str) -> bool:
        return sel.lower().strip() == key

    out: dict[str, Any] = {
        "registry_fixture_id": int(fixture_id),
        "ft_home_closing": _pick_odd(lines, mw, lambda s: mw_sel(s, "home")),
        "ft_draw_closing": _pick_odd(lines, mw, lambda s: mw_sel(s, "draw")),
        "ft_away_closing": _pick_odd(lines, mw, lambda s: mw_sel(s, "away")),
        "ou_over_25_closing": _pick_odd(
            lines,
            lambda n, s: _is_ou_line(n, s, "2.5") and "over" in s.lower(),
            lambda _s: True,
        ),
        "ou_under_25_closing": _pick_odd(
            lines,
            lambda n, s: _is_ou_line(n, s, "2.5") and "under" in s.lower(),
            lambda _s: True,
        ),
        "ou_over_15_closing": _pick_odd(
            lines,
            lambda n, s: _is_ou_line(n, s, "1.5") and "over" in s.lower(),
            lambda _s: True,
        ),
        "ou_under_15_closing": _pick_odd(
            lines,
            lambda n, s: _is_ou_line(n, s, "1.5") and "under" in s.lower(),
            lambda _s: True,
        ),
        "ou_over_35_closing": _pick_odd(
            lines,
            lambda n, s: _is_ou_line(n, s, "3.5") and "over" in s.lower(),
            lambda _s: True,
        ),
        "ou_under_35_closing": _pick_odd(
            lines,
            lambda n, s: _is_ou_line(n, s, "3.5") and "under" in s.lower(),
            lambda _s: True,
        ),
        "btts_yes_closing": _pick_odd(
            lines,
            lambda n, _s: "both teams" in n.lower() or n.lower() == "btts",
            lambda s: s.lower().strip() in {"yes", "btts: yes"},
        ),
        "btts_no_closing": _pick_odd(
            lines,
            lambda n, _s: "both teams" in n.lower() or n.lower() == "btts",
            lambda s: s.lower().strip() in {"no", "btts: no"},
        ),
    }
    if not any(out.get(k) for k in ("ft_home_closing", "ft_away_closing", "ou_over_25_closing")):
        return None
    return out


def _assemble_from_lambdas(
    *,
    fixture_id: int,
    registry_fixture_id: int | None,
    fixture_row: dict[str, Any],
    lambda_home: float,
    lambda_away: float,
    data_quality_score: float,
    prediction_source: str,
    raw_features: dict[str, Any],
) -> dict[str, Any]:
    dist = generate_score_distribution(lambda_home, lambda_away)
    if not dist:
        return {}
    top_10 = [
        {
            "scoreline": e["scoreline"],
            "probability": round(float(e["probability"]), 6),
            "rank": int(e["rank"]),
            "home_goals": int(e["home_goals"]),
            "away_goals": int(e["away_goals"]),
        }
        for e in dist[:10]
    ]
    top_3 = [e["scoreline"] for e in top_10[:3]]
    top_5 = [e["scoreline"] for e in top_10[:5]]
    top_1 = top_10[0]["scoreline"]
    confidence = float(top_10[0]["probability"])
    return {
        "fixture_id": fixture_id,
        "registry_fixture_id": registry_fixture_id,
        "competition_key": fixture_row.get("competition_key"),
        "home_team": fixture_row.get("home_team"),
        "away_team": fixture_row.get("away_team"),
        "kickoff_utc": fixture_row.get("kickoff_utc"),
        "generated_at": _utc_now(),
        "model_version": MODEL_VERSION,
        "lambda_home": round(float(lambda_home), 6),
        "lambda_away": round(float(lambda_away), 6),
        "top_10_scorelines": top_10,
        "top_1_score": top_1,
        "top_3_scores": top_3,
        "top_5_scores": top_5,
        "confidence_score": round(confidence, 6),
        "data_quality_score": round(float(data_quality_score), 4),
        "raw_features": raw_features,
        "prediction_source": prediction_source,
    }


def build_ecse_live_prediction(
    conn: sqlite3.Connection,
    fixture_id: int,
    fixture_row: dict[str, Any] | None = None,
    *,
    prematch_bundle: Any | None = None,
) -> dict[str, Any] | None:
    """Build ECSE exact-score prediction for a live fixture (no WDE / no retrain)."""
    if fixture_row is None:
        fixture_row = {}
        fx = conn.execute(
            """
            SELECT fixture_id, home_team, away_team, kickoff_utc, status, competition_key
            FROM fixtures WHERE fixture_id = ?
            """,
            (int(fixture_id),),
        ).fetchone()
        if fx:
            fixture_row = dict(fx)

    if prematch_bundle is not None:
        return build_ecse_live_prediction_from_prematch(conn, prematch_bundle, fixture_row)

    resolved = resolve_registry_fixture_id(conn, fixture_id)
    registry_id = resolved.get("registry_fixture_id")

    if registry_id is not None:
        lambdas = _load_lambda(conn, registry_id)
        precomputed = _load_top_scores(conn, registry_id, limit=10)
        if lambdas and precomputed:
            top_10 = [
                {
                    "scoreline": s["scoreline"],
                    "probability": s["probability"],
                    "rank": s["rank"],
                    "home_goals": s["home_goals"],
                    "away_goals": s["away_goals"],
                }
                for s in precomputed
            ]
            while len(top_10) < 10:
                break
            if len(top_10) >= 1:
                return {
                    "fixture_id": fixture_id,
                    "registry_fixture_id": registry_id,
                    "competition_key": fixture_row.get("competition_key"),
                    "home_team": fixture_row.get("home_team"),
                    "away_team": fixture_row.get("away_team"),
                    "kickoff_utc": fixture_row.get("kickoff_utc"),
                    "generated_at": _utc_now(),
                    "model_version": MODEL_VERSION,
                    "lambda_home": lambdas["lambda_home"],
                    "lambda_away": lambdas["lambda_away"],
                    "top_10_scorelines": top_10,
                    "top_1_score": top_10[0]["scoreline"],
                    "top_3_scores": [s["scoreline"] for s in top_10[:3]],
                    "top_5_scores": [s["scoreline"] for s in top_10[:5]],
                    "confidence_score": top_10[0]["probability"],
                    "data_quality_score": lambdas["data_quality_score"],
                    "raw_features": {
                        "resolve": resolved,
                        "source": "registry_precomputed",
                        "distribution_method": DIST_METHOD_VERSION,
                    },
                    "prediction_source": "registry_precomputed",
                }

    odds_row = build_odds_feature_row(conn, fixture_id)
    if not odds_row:
        return None
    odds_row["registry_fixture_id"] = registry_id or int(fixture_id)
    feat = extract_lambdas(odds_row)
    if not feat:
        return None
    return _assemble_from_lambdas(
        fixture_id=fixture_id,
        registry_fixture_id=registry_id,
        fixture_row=fixture_row,
        lambda_home=float(feat["lambda_home"]),
        lambda_away=float(feat["lambda_away"]),
        data_quality_score=float(feat["data_quality_score"]),
        prediction_source="live_odds",
        raw_features={
            "resolve": resolved,
            "odds_row": odds_row,
            "lambda_features": feat,
            "source": "live_odds",
        },
    )


def build_ecse_live_prediction_from_prematch(
    conn: sqlite3.Connection,
    prematch_bundle: Any,
    fixture_row: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build ECSE prediction from multi-provider prematch bundle."""
    resolved = prematch_bundle.resolved
    fixture_id = int(resolved.fixture_id or 0)
    if fixture_id <= 0:
        return None

    fixture_row = fixture_row or {
        "fixture_id": fixture_id,
        "home_team": resolved.home_team,
        "away_team": resolved.away_team,
        "kickoff_utc": resolved.kickoff_utc,
        "competition_key": resolved.competition_key,
    }

    registry_id = resolved.registry_fixture_id
    if registry_id is None:
        reg = resolve_registry_fixture_id(conn, fixture_id)
        registry_id = reg.get("registry_fixture_id")

    if registry_id is not None:
        lambdas = _load_lambda(conn, registry_id)
        precomputed = _load_top_scores(conn, registry_id, limit=10)
        if lambdas and precomputed and len(precomputed) >= 5:
            top_10 = [
                {
                    "scoreline": s["scoreline"],
                    "probability": s["probability"],
                    "rank": s["rank"],
                    "home_goals": s["home_goals"],
                    "away_goals": s["away_goals"],
                }
                for s in precomputed
            ]
            return {
                "fixture_id": fixture_id,
                "registry_fixture_id": registry_id,
                "competition_key": fixture_row.get("competition_key"),
                "home_team": fixture_row.get("home_team"),
                "away_team": fixture_row.get("away_team"),
                "kickoff_utc": fixture_row.get("kickoff_utc"),
                "generated_at": _utc_now(),
                "model_version": MODEL_VERSION,
                "lambda_home": lambdas["lambda_home"],
                "lambda_away": lambdas["lambda_away"],
                "top_10_scorelines": top_10,
                "top_1_score": top_10[0]["scoreline"],
                "top_3_scores": [s["scoreline"] for s in top_10[:3]],
                "top_5_scores": [s["scoreline"] for s in top_10[:5]],
                "confidence_score": top_10[0]["probability"],
                "data_quality_score": lambdas["data_quality_score"],
                "raw_features": {
                    "source": "registry_precomputed",
                    "coverage": prematch_bundle.coverage,
                    "resolve": resolved.resolve_sources,
                },
                "prediction_source": "registry_precomputed",
            }

    odds_row = dict(prematch_bundle.odds_row)
    if not odds_row:
        odds_row = build_odds_feature_row(conn, fixture_id) or {}
    if not odds_row:
        return None

    odds_row["registry_fixture_id"] = registry_id or fixture_id
    feat = extract_lambdas(odds_row)
    if not feat:
        return None

    raw_features = {
        "source": "multi_provider_live",
        "coverage": prematch_bundle.coverage,
        "resolve": resolved.resolve_sources,
        "odds_row": {k: v for k, v in odds_row.items() if not str(k).startswith("_")},
        "lambda_features": feat,
        "xg_available": prematch_bundle.xg is not None,
        "lineups_available": prematch_bundle.lineups is not None,
        "injuries_count": len(prematch_bundle.injuries or []),
        "correct_score_odds": prematch_bundle.correct_score_odds,
        "providers_merged": odds_row.get("_providers_merged", []),
    }
    return _assemble_from_lambdas(
        fixture_id=fixture_id,
        registry_fixture_id=registry_id,
        fixture_row=fixture_row,
        lambda_home=float(feat["lambda_home"]),
        lambda_away=float(feat["lambda_away"]),
        data_quality_score=float(feat["data_quality_score"]),
        prediction_source="multi_provider_live",
        raw_features=raw_features,
    )
