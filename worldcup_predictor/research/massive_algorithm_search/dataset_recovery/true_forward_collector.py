"""
Research-only true-forward collector (inactive by default).

Does not alter public routing, Canonical WDE/ECSE, or auto-promote.
Does not predict after kickoff. Does not overwrite freezes.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
RESEARCH_STORE = ROOT / "data" / "research" / "true_forward_collection"
SCHEMA_VERSION = "tf_collector_v1"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def plan_collection() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "cohort": "TRUE_FORWARD",
        "active": False,
        "steps": [
            "daily_fixture_discovery",
            "early_prematch_collection",
            "near_kickoff_refresh",
            "final_freeze_before_kickoff",
            "result_sync",
            "evaluation",
            "daily_report",
        ],
        "collect_fields": [
            "fixture_metadata",
            "fresh_legitimate_odds",
            "canonical_wde_read_only",
            "canonical_ecse_read_only",
            "lambda_v2_if_available",
            "locked_specialists_if_available",
            "locked_meta_if_available",
            "explicit_no_bet_reasons",
            "data_completeness",
            "configuration_hashes",
            "timestamps",
            "immutable_freeze_hash",
        ],
        "optional_models_status_not_fabricated": ["Exact_V2", "DNA", "Twins", "HCEE"],
        "guards": {
            "no_prediction_after_kickoff": True,
            "no_duplicate_freeze": True,
            "no_public_routing_changes": True,
            "no_model_promotion": True,
            "bounded_concurrency": True,
            "provider_quota_guard": True,
            "disk_guard": True,
            "idempotent_resume": True,
        },
        "storage": str(RESEARCH_STORE.relative_to(ROOT)).replace("\\", "/"),
        "generated_at": _utc(),
    }


def dry_run() -> dict[str, Any]:
    plan = plan_collection()
    RESEARCH_STORE.mkdir(parents=True, exist_ok=True)
    path = RESEARCH_STORE / "collector_plan.json"
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return {
        "status": "DRY_RUN_ONLY",
        "collection_active": False,
        "timers_active": False,
        "plan_path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "not_publicly_deployed": True,
        "canonical_unchanged": True,
        "wde_unchanged": True,
        "ecse_unchanged": True,
        "no_auto_promotion": True,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Research-only true-forward collector")
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--activate", action="store_true", help="Rejected unless explicitly approved later")
    args = ap.parse_args(argv)
    if args.activate:
        print(json.dumps({"status": "ACTIVATION_BLOCKED", "reason": "requires_explicit_owner_approval_workflow"}))
        return 2
    print(json.dumps(dry_run(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
