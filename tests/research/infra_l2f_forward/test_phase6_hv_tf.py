"""Phase 6 HV true-forward unit tests."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from worldcup_predictor.research.infra_l2f_forward.daily_universe import (
    CLASS_ELIGIBLE,
    CLASS_EXCLUDED,
    EXCL_ALREADY_STARTED,
    EXCL_DUPLICATE,
    EXCL_FRIENDLY,
    EXCL_UNSUPPORTED,
    build_daily_universe,
    classify_discovered_fixture,
    market_balance_bucket,
    odds_strength_bucket,
)
from worldcup_predictor.research.infra_l2f_forward.diversity_sampling import (
    assert_reproducible,
    sample_eligible_fixtures,
)
from worldcup_predictor.research.infra_l2f_forward.hv_batch import (
    ensure_hv_schema,
    promotion_gate_for_next_stage,
    run_hv_true_forward_day,
    stage_name_for_cap,
)
from worldcup_predictor.research.infra_l2f_forward.storage_policy import storage_outlook


def _future_ko(hours: int = 12) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def test_classify_exclusions_and_eligible():
    now = datetime.now(timezone.utc)
    assert classify_discovered_fixture(
        fixture_id=1,
        competition_key="eliteserien",
        status="NS",
        kickoff_utc=_future_ko(),
        validation_tier="B",
        now=now,
    ) == (CLASS_ELIGIBLE, None)
    assert classify_discovered_fixture(
        fixture_id=2,
        competition_key="friendlies",
        status="NS",
        kickoff_utc=_future_ko(),
        validation_tier="B",
        now=now,
    )[1] == EXCL_FRIENDLY
    assert classify_discovered_fixture(
        fixture_id=3,
        competition_key="some_random_league",
        status="NS",
        kickoff_utc=_future_ko(),
        validation_tier=None,
        now=now,
    )[1] == EXCL_UNSUPPORTED
    assert classify_discovered_fixture(
        fixture_id=4,
        competition_key="eliteserien",
        status="1H",
        kickoff_utc=_future_ko(),
        validation_tier="B",
        now=now,
    )[1] == EXCL_ALREADY_STARTED
    seen = {5}
    assert classify_discovered_fixture(
        fixture_id=5,
        competition_key="eliteserien",
        status="NS",
        kickoff_utc=_future_ko(),
        validation_tier="B",
        now=now,
        seen_ids=seen,
    )[1] == EXCL_DUPLICATE


def test_no_outcome_based_sampling_and_reproducible():
    eligible = []
    for i in range(30):
        eligible.append(
            {
                "fixture_id": 1000 + i,
                "competition_key": ["eliteserien", "superettan", "one_lyga", "virsliga", "a_lyga"][i % 5],
                "odds_strength_bucket": ["heavy_favorite", "open", "moderate_favorite"][i % 3],
                "market_balance_bucket": ["one_sided", "balanced", "mild_skew"][i % 3],
                "expected_total_bucket": ["high_et_proxy", "mid_et_proxy", "low_et_proxy"][i % 3],
                # Poison fields that must never affect selection
                "model_top1": "9-9" if i % 2 else "1-0",
                "actual_score": "2-1",
                "no_bet": i % 2 == 0,
            }
        )
    assert assert_reproducible(eligible, daily_cap=12, seed="test-seed")
    a = sample_eligible_fixtures(eligible, daily_cap=12, seed="test-seed")
    b = sample_eligible_fixtures(eligible, daily_cap=12, seed="test-seed")
    assert a["selected_fixture_ids"] == b["selected_fixture_ids"]
    # Different seed → different order/selection possible
    c = sample_eligible_fixtures(eligible, daily_cap=12, seed="other-seed")
    assert "selected_fixture_ids" in c
    # League soft diversity: with 5 leagues and cap 12, soft share ~2; pass2 may exceed
    leagues = a["league_distribution"]
    assert len(leagues) >= 3
    # no_bet / outcomes not in selection criteria
    assert all("actual_score" not in str(a.get("reproducibility")) for _ in [0])


def test_league_diversity_soft_cap_when_alternatives_exist():
    eligible = []
    for i in range(40):
        league = "eliteserien" if i < 30 else f"league_{i}"
        eligible.append(
            {
                "fixture_id": 2000 + i,
                "competition_key": league,
                "odds_strength_bucket": "open",
                "market_balance_bucket": "balanced",
                "expected_total_bucket": "mid_et_proxy",
            }
        )
    out = sample_eligible_fixtures(eligible, daily_cap=10, seed="div-seed")
    # Soft cap 20% of 10 = 2 for pass1; pass2 fills — eliteserien should not be 100%
    assert out["league_distribution"].get("eliteserien", 0) < 10


def test_odds_buckets_prematch_only():
    assert odds_strength_bucket(1.25, 6.0, 9.0) == "heavy_favorite"
    assert market_balance_bucket(1.25, 6.0, 9.0) == "one_sided"
    assert market_balance_bucket(2.40, 3.40, 2.75) == "balanced"


def test_universe_from_payload_no_writes(tmp_path):
    matches = [
        {
            "fixture_id": 11,
            "home_team": "A",
            "away_team": "B",
            "competition_key": "eliteserien",
            "validation_tier": "B",
            "status": "NS",
            "kickoff_utc": _future_ko(20),
        },
        {
            "fixture_id": 12,
            "home_team": "C",
            "away_team": "D",
            "competition_key": "friendlies",
            "validation_tier": "B",
            "status": "NS",
            "kickoff_utc": _future_ko(20),
        },
        {
            "fixture_id": 11,
            "home_team": "A",
            "away_team": "B",
            "competition_key": "eliteserien",
            "validation_tier": "B",
            "status": "NS",
            "kickoff_utc": _future_ko(20),
        },
    ]
    uni = build_daily_universe(
        target_date="2099-01-01",
        discovery_payload={"matches": matches, "count": 3},
    )
    assert uni["discovered_count"] == 3
    assert uni["eligible_count"] == 1
    assert uni["exclusion_counts"].get(EXCL_FRIENDLY) == 1
    assert uni["exclusion_counts"].get(EXCL_DUPLICATE) == 1
    assert uni["policy_notes"]["no_bet_never_excludes"] is True


def test_hv_dry_run_batch_idempotent_checkpoint(tmp_path, monkeypatch):
    fi = sqlite3.connect(":memory:")
    eval_conn = sqlite3.connect(":memory:")
    ensure_hv_schema(fi)

    matches = []
    for i in range(8):
        matches.append(
            {
                "fixture_id": 3000 + i,
                "home_team": f"H{i}",
                "away_team": f"A{i}",
                "competition_key": ["eliteserien", "superettan", "one_lyga", "virsliga"][i % 4],
                "validation_tier": "B",
                "status": "NS",
                "kickoff_utc": _future_ko(30),
            }
        )

    def fake_universe(**kwargs):
        return build_daily_universe(
            target_date=kwargs["target_date"],
            discovery_payload={"matches": matches},
        )

    monkeypatch.setattr(
        "worldcup_predictor.research.infra_l2f_forward.hv_batch.build_daily_universe",
        fake_universe,
    )
    monkeypatch.setattr(
        "worldcup_predictor.research.infra_l2f_forward.hv_batch.df_line",
        lambda: "/dev/sda1 100G 80G 20G 80% /",
    )

    r1 = run_hv_true_forward_day(
        vienna_date="2099-07-31",
        daily_cap=5,
        dry_run=True,
        seed="unit",
        prod_conn=fi,
        eval_conn=eval_conn,
        fi_conn=fi,
        artifact_root=tmp_path / "a1",
    )
    assert r1.stage == "stage1_dry_run"
    assert r1.selected == 5
    assert r1.processed == 5
    assert r1.promotion_occurred is False
    assert (tmp_path / "a1" / "universe.json").exists() or Path(r1.artifact_dir).joinpath("universe.json").exists()

    # Resume should skip already-done items when same checkpoint
    r2 = run_hv_true_forward_day(
        vienna_date="2099-07-31",
        daily_cap=5,
        dry_run=True,
        seed="unit",
        prod_conn=fi,
        eval_conn=eval_conn,
        fi_conn=fi,
        artifact_root=tmp_path / "a2",
        resume_checkpoint_id=r1.checkpoint_id,
    )
    assert r2.processed == 0  # all already recorded


def test_disk_stop_gate(tmp_path, monkeypatch):
    fi = sqlite3.connect(":memory:")
    eval_conn = sqlite3.connect(":memory:")
    monkeypatch.setattr(
        "worldcup_predictor.research.infra_l2f_forward.hv_batch.df_line",
        lambda: "/dev/sda1 100G 95G 5.0G 95% /",
    )
    monkeypatch.setattr(
        "worldcup_predictor.research.infra_l2f_forward.hv_batch.build_daily_universe",
        lambda **kwargs: {
            "discovered_count": 0,
            "eligible_count": 0,
            "excluded_count": 0,
            "exclusion_counts": {},
            "eligible_by_league": {},
            "fixtures": [],
        },
    )
    r = run_hv_true_forward_day(
        vienna_date="2099-07-31",
        daily_cap=20,
        dry_run=True,
        prod_conn=fi,
        eval_conn=eval_conn,
        fi_conn=fi,
        artifact_root=tmp_path / "disk",
        min_free_gb=8.0,
    )
    assert r.stopped_reason and "disk_free_below" in r.stopped_reason


def test_live_batch_isolates_shadow_and_never_promotes(tmp_path, monkeypatch):
    fi = sqlite3.connect(":memory:")
    eval_conn = sqlite3.connect(":memory:")

    matches = [
        {
            "fixture_id": 4001,
            "home_team": "H",
            "away_team": "A",
            "competition_key": "eliteserien",
            "validation_tier": "B",
            "status": "NS",
            "kickoff_utc": _future_ko(40),
            "prediction_scope": "owner_shadow",
        }
    ]

    monkeypatch.setattr(
        "worldcup_predictor.research.infra_l2f_forward.hv_batch.build_daily_universe",
        lambda **kwargs: build_daily_universe(
            target_date=kwargs["target_date"], discovery_payload={"matches": matches}
        ),
    )
    monkeypatch.setattr(
        "worldcup_predictor.research.infra_l2f_forward.hv_batch.df_line",
        lambda: "/dev/sda1 100G 80G 20G 80% /",
    )

    def fake_processor(ctx):
        return {
            "status": "ok",
            "canonical_status": "success",
            "freeze_id": "freeze-1",
            "freeze_hash": "abc",
            "shadow_status": "success",
            "shadow_job_id": "job-1",
            "cohort_type": "true_forward",
            "canonical_unaffected": True,
        }

    r = run_hv_true_forward_day(
        vienna_date="2099-07-31",
        daily_cap=20,
        dry_run=False,
        seed="live",
        prod_conn=fi,
        eval_conn=eval_conn,
        fi_conn=fi,
        artifact_root=tmp_path / "live",
        fixture_processor=fake_processor,
    )
    assert r.stage == "stage2_cap20"
    assert r.canonical_success == 1
    assert r.shadow_success == 1
    assert r.promotion_occurred is False
    assert r.routing_activation_occurred is False
    gate = promotion_gate_for_next_stage(
        canonical_success=1,
        canonical_attempted=1,
        shadow_success=1,
        shadow_attempted=1,
        freeze_mutations=0,
        disk_free_gb=20.0,
    )
    assert gate["may_increase_cap"] is True
    assert gate["model_promotion_allowed"] is False


def test_stage_names_and_storage_outlook():
    assert stage_name_for_cap(20, dry_run=True) == "stage1_dry_run"
    assert stage_name_for_cap(20, dry_run=False) == "stage2_cap20"
    assert stage_name_for_cap(50, dry_run=False) == "stage3_cap50"
    assert stage_name_for_cap(100, dry_run=False) == "stage4_cap100"
    outlook = storage_outlook(fixtures_per_day=100)
    assert outlook["d30"]["total_gb"] > 0
    assert outlook["retention"]["runtime_disk_rules"]["stop_new_batch_if_free_gb_below"] == 8.0


def test_cohort_separation_constant():
    from worldcup_predictor.research.infra_l2f_forward.forward_hook import resolve_cohort_type

    assert resolve_cohort_type(backfill=True, freeze_meta={"cohort_type": "true_forward"}) != "true_forward"
    assert resolve_cohort_type(backfill=False, freeze_meta={}) == "true_forward"
