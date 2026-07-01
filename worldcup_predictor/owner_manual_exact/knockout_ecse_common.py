"""Shared ECSE layer/completeness helpers for owner knockout pipeline."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner.euro_b_fixture_selector import _odds_flags
from worldcup_predictor.research.ecse_live.prediction_builder import build_odds_feature_row
from worldcup_predictor.research.ecse_live.store import get_snapshot, has_snapshot
from worldcup_predictor.research.ecse_lambda_extraction import extract_lambdas

LAYER_WEIGHTS: dict[str, float] = {
    "market_odds": 0.30,
    "provider_predictions": 0.15,
    "team_history": 0.10,
    "standings": 0.08,
    "xg": 0.12,
    "pressure": 0.10,
    "lineups": 0.08,
    "injuries": 0.07,
}


def _has_enrichment(repo: FootballIntelligenceRepository, fixture_id: int, key: str) -> bool:
    row = repo.get_fixture_enrichment_row(fixture_id)
    if not row:
        return False
    blob = row.get("payload_json") or row.get("enrichment_json")
    if not blob:
        return False
    try:
        data = json.loads(blob) if isinstance(blob, str) else blob
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(data, dict) and data.get(key) is not None


def _has_provider_predictions(repo: FootballIntelligenceRepository, fixture_id: int) -> bool:
    enrich = repo.get_sportmonks_fixture_enrichment_by_api_fixture_id(fixture_id)
    if enrich and int(enrich.get("premium_predictions_available") or 0):
        return True
    wde = repo.get_worldcup_stored_prediction(fixture_id)
    return bool(wde and wde.get("payload_json"))


def _has_standings_or_history(repo: FootballIntelligenceRepository, fixture_id: int) -> tuple[bool, bool]:
    standings = _has_enrichment(repo, fixture_id, "standings")
    history = _has_enrichment(repo, fixture_id, "recent_form") or _has_enrichment(repo, fixture_id, "head_to_head")
    return standings, history


def compute_ecse_layers(
    conn: sqlite3.Connection,
    repo: FootballIntelligenceRepository,
    *,
    fixture_id: int,
) -> tuple[list[str], list[str], float]:
    """Return (layers_used, layers_missing, completeness_score)."""
    fid = int(fixture_id)
    used: list[str] = []
    missing: list[str] = []

    odds = _odds_flags(conn, fid)
    if odds.get("has_odds") and odds.get("odds_1x2"):
        used.append("market_odds")
    else:
        missing.append("market_odds")

    if _has_provider_predictions(repo, fid):
        used.append("provider_predictions")
    else:
        missing.append("provider_predictions")

    standings, history = _has_standings_or_history(repo, fid)
    if history:
        used.append("team_history")
    else:
        missing.append("team_history")
    if standings:
        used.append("standings")
    else:
        missing.append("standings")

    if repo.has_xg_snapshot(fid):
        used.append("xg")
    else:
        missing.append("xg")

    if _has_enrichment(repo, fid, "pressure"):
        used.append("pressure")
    else:
        missing.append("pressure")

    if _has_enrichment(repo, fid, "lineups") or _has_enrichment(repo, fid, "formations"):
        used.append("lineups")
    else:
        missing.append("lineups")

    if _has_enrichment(repo, fid, "injuries"):
        used.append("injuries")
    else:
        missing.append("injuries")

    score = sum(LAYER_WEIGHTS.get(layer, 0.05) for layer in used)
    return used, missing, round(min(score, 1.0), 4)


def minimum_ecse_inputs_met(
    conn: sqlite3.Connection,
    repo: FootballIntelligenceRepository,
    *,
    fixture_id: int,
    home_team: str,
    away_team: str,
    kickoff_utc: str | None,
) -> tuple[bool, str]:
    if not fixture_id or not home_team or not away_team or not kickoff_utc:
        return False, "missing_fixture_core_fields"

    odds = _odds_flags(conn, int(fixture_id))
    if odds.get("has_odds") and odds.get("odds_1x2"):
        return True, "odds_available"

    if _has_provider_predictions(repo, int(fixture_id)):
        return True, "provider_predictions_available"

    row = build_odds_feature_row(conn, int(fixture_id))
    if row and extract_lambdas(row):
        return True, "lambda_inputs_from_odds_row"

    return False, "no_reliable_odds_or_predictions"


def ecse_generation_reason(
    conn: sqlite3.Connection,
    repo: FootballIntelligenceRepository,
    *,
    fixture_id: int,
    home_team: str,
    away_team: str,
    kickoff_utc: str | None,
) -> str:
    if has_snapshot(conn, int(fixture_id)):
        snap = get_snapshot(conn, int(fixture_id)) or {}
        src = str(snap.get("prediction_source") or "ecse_production")
        raw = snap.get("raw_features") or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        layers = raw.get("ecse_layers_used") or []
        completeness = raw.get("ecse_completeness_score")
        if layers:
            return f"ecse_exists:{src}:layers={','.join(layers)}:completeness={completeness}"
        return f"ecse_exists:{src}"

    ok, reason = minimum_ecse_inputs_met(
        conn,
        repo,
        fixture_id=int(fixture_id),
        home_team=home_team,
        away_team=away_team,
        kickoff_utc=kickoff_utc,
    )
    if ok:
        return f"ecse_not_generated:minimum_inputs_met:{reason}"
    return f"ecse_not_generated:{reason}"
