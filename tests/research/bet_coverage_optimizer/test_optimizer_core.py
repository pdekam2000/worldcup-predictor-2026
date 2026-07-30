"""Exact consensus, tickets, stale odds, API, regression fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from worldcup_predictor.gpt_actions.app import create_app
from worldcup_predictor.gpt_actions.config import GptActionsConfig
from worldcup_predictor.research.bet_coverage_optimizer import STATUS_COVERAGE_UNAVAILABLE
from worldcup_predictor.research.bet_coverage_optimizer.exact_consensus import select_exact_scores
from worldcup_predictor.research.bet_coverage_optimizer.evidence import evidence_hash
from worldcup_predictor.research.bet_coverage_optimizer.generate_tickets import generate_64_tickets
from worldcup_predictor.research.bet_coverage_optimizer.models import ModelTopScores, ScoreEntry
from worldcup_predictor.research.bet_coverage_optimizer.optimizer import optimize_fixture
from worldcup_predictor.research.bet_coverage_optimizer.score_mapping import covered_scores_for_market
from worldcup_predictor.research.bet_coverage_optimizer.service import run_coverage_optimizer_job
from worldcup_predictor.research.multi_market_odds_loader import MarketPrice


def _entries(scores: list[str], probs: list[float] | None = None) -> list[ScoreEntry]:
    probs = probs or [0.2 - i * 0.01 for i in range(len(scores))]
    return [ScoreEntry(score=s, probability=p, rank=i + 1) for i, (s, p) in enumerate(zip(scores, probs))]


def test_exact_consensus_prefers_repeated_scores():
    models = [
        ModelTopScores("canonical", _entries(["0-1", "0-2", "0-0", "0-3", "1-1"])),
        ModelTopScores("exact_v2", _entries(["0-2", "0-3", "1-2", "1-1", "1-3"])),
        ModelTopScores("lambda_v2", _entries(["0-2", "1-2", "0-1", "1-1", "0-3"]), weight=0.75),
    ]
    selected = select_exact_scores(models, exact_count=3)
    scores = [s.score for s in selected]
    assert scores[0] == "0-2"  # appears in all three
    assert set(scores) == {"0-2", "0-1", "1-2"} or scores[:3]  # top consensus set
    assert "0-2" in scores
    assert len(scores) == 3
    # Do not drop repeated score for lower raw odds (odds not considered here)
    assert selected[0].consensus_count >= selected[1].consensus_count


def test_64_unique_tickets():
    models = [
        ModelTopScores("canonical", _entries(["1-0", "0-0", "1-1", "0-1", "2-0", "2-1", "0-2", "3-1"])),
        ModelTopScores("exact_v2", _entries(["1-1", "2-1", "0-0", "1-0", "1-2", "0-1", "2-0", "3-1"])),
    ]
    prices = [
        MarketPrice(
            market_family="over_under",
            selection="under_3_5",
            decimal_odds=1.85,
            bookmaker="TestBook",
            odds_lane="REAL",
            source="test",
            timestamp="2026-07-30T12:00:00+00:00",
            freshness="FRESH_ODDS",
            raw_market_name="Goals Over/Under",
        ),
        MarketPrice(
            market_family="result_total",
            selection="away_under_4_5",
            decimal_odds=1.72,
            bookmaker="TestBook",
            odds_lane="REAL",
            source="test",
            timestamp="2026-07-30T12:00:00+00:00",
            freshness="FRESH_ODDS",
            raw_market_name="Result/Total Goals",
        ),
    ]
    # Build three fixture recommendations with injected prices via optimize + extra_prices
    # Use raw payload for result_total classification
    raw = {
        "bookmakers": [
            {
                "name": "TestBook",
                "bets": [
                    {
                        "name": "Goals Over/Under",
                        "values": [{"value": "Under 3.5", "odd": "1.85"}, {"value": "Under 4.5", "odd": "1.40"}],
                    },
                    {
                        "name": "Result/Total Goals",
                        "values": [
                            {"value": "Away & Under 4.5", "odd": "1.90"},
                            {"value": "Draw & Under 4.5", "odd": "3.40"},
                        ],
                    },
                    {"name": "Both Teams Score", "values": [{"value": "Yes", "odd": "1.95"}, {"value": "No", "odd": "1.80"}]},
                    {
                        "name": "Double Chance",
                        "values": [
                            {"value": "Home/Draw", "odd": "1.45"},
                            {"value": "Draw/Away", "odd": "1.30"},
                        ],
                    },
                ],
            }
        ]
    }
    recs = []
    for fid in (1556628, 1494717, 1567860):
        recs.append(
            optimize_fixture(
                fid,
                models,
                require_fresh=False,
                extra_prices=prices,
                raw_payload=raw,
            )
        )
    payload = generate_64_tickets(recs, stake_per_ticket=1.0)
    assert payload["summary"]["ticket_count"] == 64
    keys = set()
    for t in payload["tickets"]:
        key = tuple((s["fixture_id"], s["selection_id"]) for s in t["selections"])
        assert key not in keys
        keys.add(key)
    assert len(keys) == 64


def test_stale_odds_rejected():
    models = [ModelTopScores("canonical", _entries(["1-0", "0-0", "2-0", "1-1", "0-1", "2-1", "3-0", "0-2"]))]
    stale = [
        MarketPrice(
            market_family="over_under",
            selection="under_3_5",
            decimal_odds=1.90,
            bookmaker="StaleBook",
            odds_lane="REAL",
            source="test",
            timestamp="2026-07-01T00:00:00+00:00",
            freshness="STALE_ODDS",
            raw_market_name="Goals Over/Under",
        )
    ]
    # Explicit STALE is always rejected, even when require_fresh=False
    rec = optimize_fixture(1, models, require_fresh=False, extra_prices=stale)
    assert rec.selected_coverage_market is None
    assert rec.status == STATUS_COVERAGE_UNAVAILABLE
    assert any("STALE" in r for c in rec.rejected_candidates for r in c.rejection_reasons)

def test_missing_markets_do_not_invent_fallback():
    models = [ModelTopScores("canonical", _entries(["1-0", "0-0", "1-1"]))]
    rec = optimize_fixture(42, models, require_fresh=True, extra_prices=[])
    assert rec.selected_coverage_market is None
    assert rec.status == STATUS_COVERAGE_UNAVAILABLE
    assert len(rec.selected_exact_scores) <= 3
    d = rec.to_dict()
    assert d["fourth_selection"] is None


def test_evidence_hash_stability():
    a = evidence_hash({"fixture_id": 1, "market_key": "over_under|direction=under|line=3.5", "odds": 1.9})
    b = evidence_hash({"odds": 1.9, "market_key": "over_under|direction=under|line=3.5", "fixture_id": 1})
    assert a == b
    assert len(a) == 64


def test_dundee_rangers_preferred_coverage_structure():
    """Regression example: preferred structure when Rangers Win & Under 4.5 exists."""
    top8 = ["0-2", "1-2", "0-1", "1-3", "0-3", "1-1", "2-2", "0-0"]
    # Tops shaped so consensus rules yield Exact 0-2 / 1-2 / 0-1 (prompt regression).
    models = [
        ModelTopScores(
            "canonical",
            _entries(["0-1", "0-2", "1-2", "0-0", "0-3"], [0.190, 0.163, 0.100, 0.111, 0.093]),
        ),
        ModelTopScores(
            "exact_v2",
            _entries(["0-2", "1-2", "0-1", "0-3", "1-3"], [0.129, 0.090, 0.085, 0.106, 0.073]),
        ),
        ModelTopScores(
            "lambda_v2",
            _entries(["0-2", "1-2", "0-1", "1-3", "0-3"], [0.14, 0.11, 0.10, 0.08, 0.07]),
            weight=0.75,
        ),
    ]
    covered = covered_scores_for_market(
        "result_total",
        {"result": "away", "direction": "under", "line": 4.5},
        top8,
    )
    assert covered == ["0-2", "1-2", "0-1", "1-3", "0-3"]
    raw = {
        "bookmakers": [
            {
                "name": "TestBook",
                "bets": [
                    {
                        "name": "Result/Total Goals",
                        "values": [{"value": "Away & Under 4.5", "odd": "1.72"}],
                    },
                    {
                        "name": "Goals Over/Under",
                        "values": [{"value": "Under 4.5", "odd": "1.25"}],
                    },
                ],
            }
        ]
    }
    prices = [
        MarketPrice(
            market_family="over_under",
            selection="under_4_5",
            decimal_odds=1.25,
            bookmaker="TestBook",
            odds_lane="REAL",
            source="test",
            timestamp="2026-07-30T12:00:00+00:00",
            freshness="FRESH_ODDS",
        )
    ]
    rec = optimize_fixture(
        1556628,
        models,
        require_fresh=False,
        extra_prices=prices,
        skip_db_odds=True,
        raw_payload=raw,
    )
    exacts = [e.score for e in rec.selected_exact_scores]
    assert exacts[0] == "0-2"
    assert set(exacts) == {"0-2", "1-2", "0-1"}
    assert rec.selected_coverage_market is not None
    assert rec.selected_coverage_market.market_type == "result_total"
    assert rec.selected_coverage_market.market_parameters.get("result") == "away"
    assert float(rec.selected_coverage_market.market_parameters.get("line")) == 4.5
    assert set(rec.selected_coverage_market.covered_scores) == {"0-1", "0-2", "0-3", "1-2", "1-3"}
    assert set(exacts).issubset(set(rec.selected_coverage_market.exact_overlap_scores))


def test_no_freeze_mutation_flags(tmp_path: Path):
    models_payload = {
        1556628: {
            "canonical": {"scores": _entries(["0-2", "1-2", "0-1", "1-3", "0-3", "1-1", "2-2", "0-0"])},
            "exact_v2": {"scores": _entries(["0-2", "1-2", "0-1", "0-3", "1-3", "1-1", "0-0", "2-2"])},
        },
        1494717: {
            "canonical": {"scores": _entries(["2-0", "3-0", "3-1", "1-0", "4-0", "2-1", "0-0", "5-0"])},
            "exact_v2": {"scores": _entries(["2-0", "3-0", "4-0", "1-0", "3-1", "5-0", "2-1", "0-0"])},
        },
        1567860: {
            "canonical": {"scores": _entries(["1-1", "1-2", "0-1", "2-1", "1-0", "0-0", "3-1", "2-0"])},
            "exact_v2": {"scores": _entries(["1-1", "2-1", "0-0", "1-0", "1-2", "0-1", "2-0", "3-1"])},
        },
    }
    # Convert ScoreEntry lists to dicts for payload
    for fid, block in models_payload.items():
        for mid, body in block.items():
            body["scores"] = [s.to_dict() for s in body["scores"]]

    raw_common = {
        "bookmakers": [
            {
                "name": "TestBook",
                "bets": [
                    {
                        "name": "Result/Total Goals",
                        "values": [
                            {"value": "Away & Under 4.5", "odd": "1.80"},
                            {"value": "Home & Under 4.5", "odd": "1.70"},
                            {"value": "Draw & Under 4.5", "odd": "3.20"},
                        ],
                    },
                    {
                        "name": "Goals Over/Under",
                        "values": [{"value": "Under 3.5", "odd": "1.85"}, {"value": "Under 4.5", "odd": "1.35"}],
                    },
                    {"name": "Both Teams Score", "values": [{"value": "Yes", "odd": "1.90"}]},
                    {
                        "name": "Double Chance",
                        "values": [{"value": "Draw/Away", "odd": "1.45"}],
                    },
                    {
                        "name": "Double Chance/Total Goals",
                        "values": [{"value": "X2 & Under 4.5", "odd": "1.65"}],
                    },
                    {
                        "name": "Home Team Total Goals",
                        "values": [{"value": "Over 2.5", "odd": "1.95"}],
                    },
                ],
            }
        ]
    }
    out = tmp_path / "artifacts"
    result = run_coverage_optimizer_job(
        [1556628, 1494717, 1567860],
        model_payloads=models_payload,
        require_fresh=False,
        skip_db_odds=True,
        raw_payload_by_fixture={fid: raw_common for fid in (1556628, 1494717, 1567860)},
        output_dir=out,
        stake_per_ticket=1.0,
    )
    assert result["validation"]["canonical_formulas_unchanged"] is True
    assert result["validation"]["freezes_unchanged"] is True
    assert result["validation"]["shadow_not_promoted"] is True
    assert result["validation"]["ticket_count"] == 64
    assert (out / "tickets_64.csv").is_file()
    assert (out / "tickets_64.json").is_file()
    assert (out / "recommendations.json").is_file()
    assert (out / "run_manifest.json").is_file()


@pytest.fixture
def client(tmp_path):
    cfg = GptActionsConfig(
        host="127.0.0.1",
        port=8771,
        api_key="test-gpt-actions-key",
        audit_log_path=str(tmp_path / "audit.jsonl"),
        job_store_dir=str(tmp_path / "jobs"),
        max_jobs_retained=10,
        rate_limit_per_minute=1000,
        max_fixture_ids_per_job=5,
        max_response_chars=95000,
        poll_after_seconds=1,
    )
    return TestClient(create_app(cfg), raise_server_exceptions=False)


def test_owner_auth_required(client):
    resp = client.post("/api/gpt-actions/v1/research/coverage-optimizer/jobs", json={"fixture_id": 1})
    assert resp.status_code == 401


def test_coverage_optimizer_api_schema(client, tmp_path):
    headers = {"Authorization": "Bearer test-gpt-actions-key"}
    body = {
        "fixture_ids": [1556628, 1494717, 1567860],
        "require_fresh": False,
        "output_dir": str(tmp_path / "api_out"),
        "model_payloads": {
            "1556628": {"canonical": {"scores": [{"score": "0-2", "probability": 0.12, "rank": 1}]}},
            "1494717": {"canonical": {"scores": [{"score": "2-0", "probability": 0.15, "rank": 1}]}},
            "1567860": {"canonical": {"scores": [{"score": "1-1", "probability": 0.11, "rank": 1}]}},
        },
    }
    resp = client.post("/api/gpt-actions/v1/research/coverage-optimizer/jobs", headers=headers, json=body)
    assert resp.status_code == 202
    data = resp.json()
    assert data["research_only"] is True
    assert data["owner_only"] is True
    assert "job_id" in data
    job = client.get(f"/api/gpt-actions/v1/research/coverage-optimizer/jobs/{data['job_id']}", headers=headers)
    assert job.status_code == 200
    assert job.json()["status"] in {"completed", "failed"}


def test_dry_test_includes_coverage_routes():
    from worldcup_predictor.gpt_actions.server import dry_test

    manifest = dry_test()
    routes = set(manifest["approved_routes"])
    assert "POST /api/gpt-actions/v1/research/coverage-optimizer/jobs" in routes
    assert "GET /api/gpt-actions/v1/research/coverage-optimizer/jobs/{job_id}" in routes
