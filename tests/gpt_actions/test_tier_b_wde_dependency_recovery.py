"""Tier B WDE dependency recovery tests."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from worldcup_predictor.gpt_actions.competition_normalize import normalize_competition_key
from worldcup_predictor.gpt_actions.runtime_bootstrap import bootstrap_gpt_actions_runtime
from worldcup_predictor.gpt_actions.tier_b_shadow_registry import TIER_B_CANONICAL_KEYS
from worldcup_predictor.gpt_actions.wde_runtime import (
    attach_wde_execution_diagnostics,
    classify_wde_exception,
    prepare_daily_fixture_for_wde,
)
from worldcup_predictor.mcp_server.runtime import _format_prediction_result, _market_execution_status
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.owner_daily.predictions import run_daily_wde


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "raw,canonical",
    [
        ("eliteserien", "eliteserien"),
        ("urvalsdeild", "urvalsdeild"),
        ("Úrvalsdeild", "urvalsdeild"),
        ("league_103", "eliteserien"),
        ("league_164", "urvalsdeild"),
        ("allsvenskan", "allsvenskan"),
        ("veikkausliiga", "veikkausliiga"),
        ("a_lyga", "a_lyga"),
        ("virsliga", "virsliga"),
        ("superettan", "superettan"),
    ],
)
def test_tier_b_competition_normalization(raw: str, canonical: str) -> None:
    assert normalize_competition_key(raw) == canonical
    assert canonical in TIER_B_CANONICAL_KEYS


def test_bootstrap_auto_sets_production_env_when_env_production_exists(monkeypatch, tmp_path: Path) -> None:
    prod_env = tmp_path / ".env.production"
    prod_env.write_text("API_FOOTBALL_KEY=test-key\n", encoding="utf-8")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("APP_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    meta = bootstrap_gpt_actions_runtime()
    assert os.environ.get("APP_ENV") == "production"
    assert "api_cache_dir" in meta


def test_api_credentials_missing_returns_specific_failure_code() -> None:
    settings = MagicMock()
    settings.api_football_configured = False
    repo = MagicMock()
    conn = MagicMock()
    fixture = DailyFixture(
        fixture_id=1508803,
        provider_fixture_id=1508803,
        competition_key="urvalsdeild",
        home_team="A",
        away_team="B",
        kickoff_utc="2026-07-12T18:00:00",
        status="NS",
        season=2026,
    )
    status, detail = run_daily_wde(
        fixture,
        settings=settings,
        repo=repo,
        conn=conn,
        dry_run=False,
        force=True,
    )
    assert status == "skipped"
    assert detail["wde_failure_code"] == "WDE_API_CREDENTIALS_MISSING"
    assert detail["wde_execution_status"] == "blocked_missing_dependency"
    assert detail["wde_failure_dependency"] == "api_credentials"
    assert "API_FOOTBALL_KEY" in detail["wde_failure_message_sanitized"]


def test_attach_wde_execution_diagnostics_no_secrets() -> None:
    detail = attach_wde_execution_diagnostics(
        {},
        wde_execution_status="blocked_missing_dependency",
        failure_code="WDE_API_CREDENTIALS_MISSING",
        failure_dependency="api_credentials",
        failure_message_sanitized="API_FOOTBALL_KEY not loaded",
        inputs_missing=["api_credentials"],
    )
    text = str(detail).lower()
    assert "password" not in text
    assert "secret" not in text
    assert detail["wde_inputs_missing"] == ["api_credentials"]


def test_classify_unknown_competition_exception() -> None:
    code, stage = classify_wde_exception(KeyError("Unknown competition: foo"))
    assert code == "WDE_COMPETITION_UNSUPPORTED"
    assert stage == "competition_registry"


def test_market_execution_status_from_wde_payload() -> None:
    payload = {"one_x_two": {"selection": "home_win"}}
    btts = {"selection": "yes", "yes": 0.6, "no": 0.4}
    assert _market_execution_status(payload, btts, label="btts")["btts_execution_status"] == "executed"
    assert _market_execution_status(None, {}, label="btts")["btts_failure_code"] == "WDE_PAYLOAD_MISSING"


def test_format_prediction_result_includes_btts_ou_execution_status() -> None:
    payload = {
        "one_x_two": {"selection": "home_win"},
        "probabilities": {"home_win": 60, "draw": 20, "away_win": 20},
        "extended_markets": {
            "btts": {"selection": "yes", "option_a": 0.55, "option_b": 0.45},
        },
        "detailed_markets": {
            "over_under_25": {"selection": "over_2_5", "option_a": 0.6, "option_b": 0.4},
        },
    }
    result = _format_prediction_result(
        row={"fixture_id": 1, "home_team": "H", "away_team": "A", "competition_key": "urvalsdeild"},
        freshness={"odds_status": "FRESH_ODDS", "age_minutes": 1},
        payload=payload,
        ecse_snap={"top_1_score": "1-0", "confidence_score": 0.2},
        status="OK",
        warnings=[],
        wde_execution_status="executed",
        wde_result_source="fresh_engine",
        wde_detail={"wde_execution_status": "executed"},
    )
    assert result["wde"]["wde_execution_status"] == "executed"
    assert result["btts"]["btts_execution_status"] == "executed"
    assert result["quality"]["status"] == "OK"


def test_prepare_daily_fixture_registers_tier_b_competition() -> None:
    repo = MagicMock()
    repo.upsert_competition = MagicMock()
    fixture = DailyFixture(
        fixture_id=1494698,
        provider_fixture_id=1494698,
        competition_key="league_103",
        home_team="Sarpsborg",
        away_team="Viking",
        kickoff_utc="2026-07-12T17:15:00",
        status="NS",
        season=2026,
    )
    prepared = prepare_daily_fixture_for_wde(fixture, repo=repo)
    assert prepared.competition_key == "eliteserien"
    repo.upsert_competition.assert_called_once()


def test_owner_shadow_tier_b_not_public_in_delegation_labels() -> None:
    from worldcup_predictor.gpt_actions.delegation import format_fixture_evidence

    raw = {
        "fixture": {"fixture_id": 1508803, "home_team": "A", "away_team": "B", "competition": "urvalsdeild"},
        "wde": {"decision_pick": "home_win", "confidence": 30, "wde_execution_status": "executed"},
        "btts": {"prediction": "yes"},
        "over_under_2_5": {"prediction": "over_2_5"},
        "ecse": {"top_scores": [{"rank": 1, "score": "1-0", "probability": 0.1}]},
        "quality": {"status": "OK", "owner_label": "WEAK_SIGNAL"},
        "odds": {"freshness": "FRESH_ODDS"},
    }
    out = format_fixture_evidence(
        raw,
        timezone="Europe/Vienna",
        tier_meta={"tier": "B", "prediction_scope": "owner_shadow", "competition": "urvalsdeild"},
    )
    assert out["public_visible"] is False
    assert out["owner_shadow"] is True
    assert out["prediction_scope"] == "owner_shadow"
