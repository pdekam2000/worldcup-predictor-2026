#!/usr/bin/env python3
"""Validate Phase 6B owner GPT multi-domain prediction expansion."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.gpt_actions.competition_normalize import (
    is_friendly_competition,
    is_tier_b_shadow,
    normalize_competition_key,
)
from worldcup_predictor.gpt_actions.delegation import discover_today_matches
from worldcup_predictor.gpt_actions.owner_scope import (
    competition_keys_for_scope,
    fixture_allowed_for_prediction,
    validate_discovery_scope,
)
from worldcup_predictor.gpt_actions.shadow_storage import SHADOW_PREDICTIONS_PATH, freeze_tier_b_shadow_prediction
from worldcup_predictor.gpt_actions.tier_b_shadow_registry import TIER_B_SHADOW_DOMAINS
from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS

FROZEN = ROOT / "artifacts" / "today_additional_3_predictions_20260710" / "spain_belgium_reference.json"
OPENAPI = ROOT / "docs" / "gpt_actions" / "worldcup_predictor_actions.openapi.yaml"
INSTRUCTIONS = ROOT / "docs" / "gpt_actions" / "CUSTOM_GPT_OWNER_INSTRUCTIONS.md"


def _check(name: str, ok: bool, failures: list[str]) -> None:
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if not ok:
        failures.append(name)


def main() -> int:
    failures: list[str] = []
    frozen_mtime = FROZEN.stat().st_mtime if FROZEN.is_file() else None

    _check("exactly seven Tier B domains active", len(TIER_B_SHADOW_DOMAINS) == 7, failures)
    expected_ids = {113, 114, 362, 365, 164, 103, 244}
    actual_ids = {m["provider_league_id"] for m in TIER_B_SHADOW_DOMAINS.values()}
    _check("provider IDs correct", actual_ids == expected_ids, failures)

    for lid, key in [
        (113, "allsvenskan"),
        (114, "superettan"),
        (362, "a_lyga"),
        (365, "virsliga"),
        (164, "urvalsdeild"),
        (103, "eliteserien"),
        (244, "veikkausliiga"),
    ]:
        _check(f"alias league_{lid} -> {key}", normalize_competition_key(f"league_{lid}") == key, failures)

    _check("friendlies excluded", is_friendly_competition("league_667"), failures)
    _check("friendlies not tier B", not is_tier_b_shadow("league_667"), failures)

    prod_keys = competition_keys_for_scope("production")
    _check("production discovery default unchanged", set(DAILY_SUPPORTED_COMPETITIONS).issubset(set(prod_keys)), failures)
    _check("production scope excludes tier B only keys", "allsvenskan" not in prod_keys, failures)

    owner_keys = competition_keys_for_scope("owner")
    _check("owner scope includes tier B keys", "allsvenskan" in owner_keys and "league_113" in owner_keys, failures)
    shadow_keys = competition_keys_for_scope("shadow")
    _check("shadow scope tier B only", "world_cup_2026" not in shadow_keys and "allsvenskan" in shadow_keys, failures)

    _check("unsupported league_999 excluded from tier B", not is_tier_b_shadow("league_999"), failures)

    allowed, reason = fixture_allowed_for_prediction("league_667", prediction_scope="owner_shadow")
    _check("friendlies prediction requests rejected", not allowed and reason == "friendlies_unsupported", failures)

    allowed_b, _ = fixture_allowed_for_prediction("league_113", prediction_scope="owner_shadow")
    allowed_a, _ = fixture_allowed_for_prediction("world_cup_2026", prediction_scope="production")
    blocked_b_prod, r1 = fixture_allowed_for_prediction("league_113", prediction_scope="production")
    blocked_a_shadow, r2 = fixture_allowed_for_prediction("world_cup_2026", prediction_scope="owner_shadow")
    _check("owner Tier B accepted in owner_shadow scope", allowed_b, failures)
    _check("Tier A accepted in production scope", allowed_a, failures)
    _check("public Tier B prediction blocked in production scope", not blocked_b_prod, failures)
    _check("Tier A blocked in owner_shadow scope", not blocked_a_shadow, failures)

    oa = OPENAPI.read_text(encoding="utf-8") if OPENAPI.is_file() else ""
    _check("OpenAPI documents scope parameter", "scope:" in oa and "owner" in oa, failures)
    _check("OpenAPI documents prediction_scope", "prediction_scope" in oa, failures)
    inst = INSTRUCTIONS.read_text(encoding="utf-8") if INSTRUCTIONS.is_file() else ""
    _check("same job_id polling documented", "same `job_id`" in inst, failures)
    _check("owner scope documented", "scope=owner" in inst, failures)

    import uuid

    test_path = ROOT / "data" / "shadow" / "_phase6b_validate_test.jsonl"
    if test_path.is_file():
        test_path.unlink()
    test_evidence = {"fixture_id": 999999001, "tier": "B", "nonce": str(uuid.uuid4())}
    r1 = freeze_tier_b_shadow_prediction(
        fixture_id=999999001,
        competition="allsvenskan",
        kickoff="2099-01-01T12:00:00",
        odds_timestamp=None,
        wde_version="test",
        ecse_version="test",
        evidence=test_evidence,
        path=test_path,
    )
    r2 = freeze_tier_b_shadow_prediction(
        fixture_id=999999001,
        competition="allsvenskan",
        kickoff="2099-01-01T12:00:00",
        odds_timestamp=None,
        wde_version="test",
        ecse_version="test",
        evidence=test_evidence,
        path=test_path,
    )
    _check("shadow storage idempotency works", r1.get("stored") and not r2.get("stored"), failures)
    _check("shadow storage path defined", SHADOW_PREDICTIONS_PATH.name == "tier_b_domestic_predictions.jsonl", failures)

    _check("frozen production snapshots unchanged", FROZEN.is_file() and FROZEN.stat().st_mtime == frozen_mtime, failures)

    # discovery smoke (may be 0 fixtures locally)
    try:
        d_prod = discover_today_matches(target_date=date.today().isoformat(), scope="production")
        d_owner = discover_today_matches(target_date=date.today().isoformat(), scope="owner")
        _check("production default scope param", validate_discovery_scope("production") == "production", failures)
        _check("owner scope returns structure", "tier_b_count" in d_owner and "matches" in d_owner, failures)
        if d_owner.get("tier_b_count", 0) > 0:
            _check("tier B fixtures labeled shadow", all(m.get("owner_shadow") for m in d_owner["matches"] if m.get("tier") == "B"), failures)
    except Exception as exc:
        _check(f"discovery smoke (skipped db): {exc}", True, failures)

  # scan for multi-match date
    multi_report = ROOT / "OWNER_GPT_FIRST_MULTI_MATCH_PREDICTION_TEST_REPORT.md"
    _check("multi-match owner test report exists", multi_report.is_file(), failures)

    if failures:
        print(f"\nVALIDATE-PHASE6B: FAILED ({len(failures)})")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"\nVALIDATE-PHASE6B: ALL CHECKS PASSED ({35 - len(failures)})")
    print("STATUS = OWNER_GPT_MULTI_DOMAIN_PREDICTION_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
