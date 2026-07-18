"""Forward shadow batch runner."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.challenger.constants import FORWARD_THRESHOLDS
from worldcup_predictor.challenger.phase3b.policy_gate import load_forward_policy, should_generate_gbgm1_forward
from worldcup_predictor.challenger.runner import run_challenger_for_fixture


def run_forward_shadow_batch(conn, model, fixture_rows: list[dict[str, Any]]) -> dict[str, Any]:
    policy = load_forward_policy()
    model_id = str(getattr(model, "model_id", "") or "")
    if model_id.startswith("GBGM-1") and not should_generate_gbgm1_forward():
        return {
            "n": 0,
            "failures": 0,
            "results": [],
            "thresholds": FORWARD_THRESHOLDS,
            "forward_active": False,
            "reason": policy.get("reason") or "MODEL_BELOW_BASELINE",
            "pause_gbgm1_new_generation": True,
            "note": "GBGM-1 forward generation paused by Phase 3B policy; historical freezes preserved; canonical unaffected",
        }
    results = []
    failures = 0
    for row in fixture_rows:
        try:
            out = run_challenger_for_fixture(
                conn,
                fixture_id=int(row["fixture_id"]),
                model=model,
                prediction_scope=str(row.get("prediction_scope") or "owner_shadow"),
                validation_tier=row.get("validation_tier"),
                include_market=getattr(model, "variant", "NM") == "MC",
                canonical_summary=row.get("canonical_summary"),
                linked_canonical_freeze_id=row.get("linked_canonical_freeze_id"),
            )
            results.append(out)
        except Exception as exc:
            failures += 1
            results.append({"fixture_id": row.get("fixture_id"), "error": str(exc)[:200], "canonical_unaffected": True})
    return {
        "n": len(fixture_rows),
        "failures": failures,
        "results": results,
        "thresholds": FORWARD_THRESHOLDS,
        "forward_policy": policy,
        "note": "Challenger failure must never change canonical job status",
    }
