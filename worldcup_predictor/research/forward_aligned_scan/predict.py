"""Ephemeral prediction + ranking for forward aligned scan."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot
from worldcup_predictor.research.canonical_ephemeral.facade import run_ephemeral_canonical_prediction
from worldcup_predictor.research.canonical_ephemeral.types import ResearchContext
from worldcup_predictor.research.canonical_ephemeral.write_guard import get_write_attempts
from worldcup_predictor.research.forward_aligned_scan.alignment import alignment_score, classify_alignment
from worldcup_predictor.research.forward_aligned_scan.constants import (
    CALLER,
    MAX_TIER_A,
    MAX_TIER_B,
    MAX_TIER_S,
    TIER_A,
    TIER_B,
    TIER_REJECTED,
    TIER_S,
)
from worldcup_predictor.research.forward_aligned_scan.directions import derive_directions, goal_alignment
from worldcup_predictor.research.forward_aligned_scan.odds_prep import prepare_odds


def _scan_id(from_date: str, days: int) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"fas_{from_date}_{days}d_{ts}_{uuid.uuid4().hex[:8]}"


def predict_fixture(
    fixture: dict[str, Any],
    *,
    scan_id: str,
    scope: str,
    prod_conn: Any,
    settings: Settings | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    settings = settings or get_settings()
    odds_prep = prepare_odds(fixture, prod_conn=prod_conn, settings=settings, dry_run=dry_run)
    base = {
        **fixture,
        "odds_prep": odds_prep,
        "timing_class": odds_prep.get("timing_class"),
        "hours_to_kickoff": odds_prep.get("hours_to_kickoff"),
    }
    if not odds_prep.get("ready"):
        availability = str(odds_prep.get("availability") or "odds_not_ready")
        # Preserve started-fixture signal without predicting
        if availability == "BLOCKED_FIXTURE_STARTED" or str(odds_prep.get("timing_class") or "") == "STARTED_OR_PAST":
            availability = "FIXTURE_STARTED_EXCLUDED"
        return {
            **base,
            "prediction_status": availability,
            "alignment_tier": TIER_REJECTED,
            "reject_reasons": [availability],
            "selected_reason": None,
            "tier_s_failure_primary": None,
            "tier_s_failure_reasons": [],
            "zero_write": {
                "canonical_writes_attempted": 0,
                "canonical_writes_completed": 0,
                "freeze_created": False,
                "freeze_updated": False,
                "wsp_written": False,
                "ecse_canonical_written": False,
            },
        }

    # Hard gate: never predict post-kickoff fixtures
    htk = odds_prep.get("hours_to_kickoff")
    if htk is not None and float(htk) <= 0:
        return {
            **base,
            "prediction_status": "FIXTURE_STARTED_EXCLUDED",
            "alignment_tier": TIER_REJECTED,
            "reject_reasons": ["FIXTURE_STARTED_EXCLUDED"],
            "selected_reason": None,
            "tier_s_failure_primary": None,
            "tier_s_failure_reasons": [],
            "zero_write": {
                "canonical_writes_attempted": 0,
                "canonical_writes_completed": 0,
                "freeze_created": False,
                "freeze_updated": False,
                "wsp_written": False,
                "ecse_canonical_written": False,
            },
        }

    if dry_run:
        return {
            **base,
            "prediction_status": "DRY_RUN_SKIPPED_PREDICTION",
            "alignment_tier": TIER_REJECTED,
            "reject_reasons": ["dry_run"],
            "selected_reason": None,
            "zero_write": {
                "canonical_writes_attempted": 0,
                "canonical_writes_completed": 0,
                "freeze_created": False,
                "freeze_updated": False,
                "wsp_written": False,
                "ecse_canonical_written": False,
            },
        }

    snap = get_latest_valid_1x2_odds_snapshot(
        prod_conn, int(fixture["fixture_id"]), kickoff_utc=fixture.get("kickoff_utc")
    )
    ctx = ResearchContext(
        experiment_id=scan_id,
        experiment_date=str(fixture.get("vienna_date") or ""),
        snapshot_class="FORWARD_SCAN",
        audit_id=f"{scan_id}_{fixture['fixture_id']}",
        scope=scope,
        caller=CALLER,
    )
    pred = run_ephemeral_canonical_prediction(
        int(fixture["fixture_id"]),
        scope=scope,
        odds_snapshot=snap,
        research_context=ctx,
        settings=settings,
        prod_conn=prod_conn,
    )
    pred_d = pred.to_dict()
    dirs = derive_directions(
        wde=pred_d.get("wde"),
        ecse=pred_d.get("ecse"),
        odds_home=odds_prep.get("home"),
        odds_draw=odds_prep.get("draw"),
        odds_away=odds_prep.get("away"),
    )
    goals = goal_alignment(pred_d.get("ecse"), pred_d.get("btts"), pred_d.get("ou25"))
    mass = (pred_d.get("ecse") or {}).get("top5_mass")
    tier_info = classify_alignment(
        dirs=dirs,
        consensus=pred_d.get("consensus"),
        no_bet=pred_d.get("no_bet"),
        top5_mass=mass,
        odds_ready=True,
        quality_conflict=str(pred_d.get("quality_status") or "").upper() in {"FAILED"},
    )
    score = alignment_score(
        dirs=dirs,
        consensus=pred_d.get("consensus"),
        no_bet=pred_d.get("no_bet"),
        top5_mass=mass,
    )
    attempts = get_write_attempts()
    zero = {
        "canonical_writes_attempted": int(pred_d.get("canonical_writes_attempted") or len(attempts) or 0),
        "canonical_writes_completed": int(pred_d.get("canonical_writes_completed") or 0),
        "freeze_created": bool(pred_d.get("freeze_created")),
        "freeze_updated": bool(pred_d.get("freeze_updated")),
        "wsp_written": bool(pred_d.get("wsp_written")),
        "ecse_canonical_written": bool(pred_d.get("ecse_canonical_written")),
    }
    return {
        **base,
        "prediction_status": "PREDICTED" if pred_d.get("complete") else "PREDICTED_PARTIAL",
        "prediction": {
            "wde": pred_d.get("wde"),
            "btts": pred_d.get("btts"),
            "ou25": pred_d.get("ou25"),
            "ecse": pred_d.get("ecse"),
            "consensus": pred_d.get("consensus"),
            "no_bet": pred_d.get("no_bet"),
            "no_bet_diagnostics": pred_d.get("no_bet_diagnostics"),
            "no_bet_recomputed": pred_d.get("no_bet_recomputed"),
            "no_bet_decision_stage": pred_d.get("no_bet_decision_stage"),
            "no_bet_reasons": pred_d.get("no_bet_reasons"),
            "no_bet_reason_details": pred_d.get("no_bet_reason_details"),
            "no_bet_cleared_reasons": pred_d.get("no_bet_cleared_reasons"),
            "no_bet_retained_reasons": pred_d.get("no_bet_retained_reasons"),
            "baseline_no_bet": pred_d.get("baseline_no_bet"),
            "final_no_bet": pred_d.get("final_no_bet"),
            "pick_tier": pred_d.get("pick_tier"),
            "model_version": pred_d.get("model_version"),
            "model_config_hash": pred_d.get("model_config_hash"),
            "odds_content_hash": pred_d.get("odds_content_hash"),
            "research_output_hash": pred_d.get("research_output_hash"),
            "execution_mode": pred_d.get("execution_mode"),
            "warnings": pred_d.get("warnings"),
            "quality_status": pred_d.get("quality_status"),
        },
        "directions": dirs,
        "goal_alignment": goals,
        "alignment_tier": tier_info["alignment_tier"],
        "reject_reasons": tier_info.get("reject_reasons") or [],
        "selected_reason": tier_info.get("selected_reason"),
        "caution": tier_info.get("caution"),
        "tier_s_failure_primary": tier_info.get("tier_s_failure_primary"),
        "tier_s_failure_reasons": tier_info.get("tier_s_failure_reasons") or [],
        "alignment_score": score["alignment_score"],
        "alignment_score_detail": score,
        "zero_write": zero,
        "stability": "UNKNOWN_NO_PRIOR_SNAPSHOT",
        "probabilities_persisted": _probs_persisted(pred_d.get("ecse")),
    }


def _probs_persisted(ecse: dict[str, Any] | None) -> bool:
    if not ecse:
        return False
    if ecse.get("top5_mass") is None or ecse.get("top3_mass") is None or ecse.get("entropy") is None:
        return False
    for i in range(1, 6):
        t = ecse.get(f"top{i}")
        if not isinstance(t, dict) or t.get("probability") is None:
            return False
    return True


def _sort_key(row: dict[str, Any]) -> tuple:
    tier_rank = {TIER_S: 0, TIER_A: 1, TIER_B: 2, TIER_REJECTED: 9}.get(row.get("alignment_tier"), 8)
    mass = (row.get("prediction") or {}).get("ecse", {}).get("top5_mass")
    mass3 = (row.get("prediction") or {}).get("ecse", {}).get("top3_mass")
    ent = (row.get("prediction") or {}).get("ecse", {}).get("entropy")
    agree = 1 if (row.get("directions") or {}).get("wde_decision") == (row.get("directions") or {}).get(
        "ecse_top5_majority"
    ) else 0
    stable = 1 if row.get("stability") == "STABLE" else 0
    # lower entropy better → sort ascending via negative inverse; use large number if missing
    ent_key = float(ent) if ent is not None else 999.0
    htk = float(row.get("hours_to_kickoff") or 9999)
    # fresher = smaller hours age preferred among equals — use odds age
    age = ((row.get("odds_prep") or {}).get("odds_age_hours"))
    age_key = float(age) if age is not None else 999.0
    return (
        tier_rank,
        -int(row.get("alignment_score") or 0),
        -agree,
        -(float(mass) if mass is not None else -1.0),
        -(float(mass3) if mass3 is not None else -1.0),
        ent_key,
        -stable,
        age_key,
        htk,
        int(row.get("fixture_id") or 0),
    )


def select_outputs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(
        [r for r in rows if r.get("alignment_tier") in {TIER_S, TIER_A, TIER_B}],
        key=_sort_key,
    )
    tier_s = [r for r in ranked if r.get("alignment_tier") == TIER_S][:MAX_TIER_S]
    tier_a = [r for r in ranked if r.get("alignment_tier") == TIER_A][:MAX_TIER_A]
    tier_b = [r for r in ranked if r.get("alignment_tier") == TIER_B][:MAX_TIER_B]
    rejected = [r for r in rows if r.get("alignment_tier") == TIER_REJECTED]

    def stamp(items: list[dict[str, Any]], start: int = 1) -> list[dict[str, Any]]:
        out = []
        for i, r in enumerate(items, start=start):
            out.append({**r, "rank": i})
        return out

    return {
        "tier_s": stamp(tier_s),
        "tier_a": stamp(tier_a),
        "tier_b": stamp(tier_b),
        "rejected": rejected,
        "counts": {
            "tier_s_qualified": sum(1 for r in rows if r.get("alignment_tier") == TIER_S),
            "tier_a_qualified": sum(1 for r in rows if r.get("alignment_tier") == TIER_A),
            "tier_b_qualified": sum(1 for r in rows if r.get("alignment_tier") == TIER_B),
            "tier_s_selected": len(tier_s),
            "tier_a_selected": len(tier_a),
            "tier_b_selected": len(tier_b),
            "rejected": len(rejected),
        },
        "no_quota_fill": True,
    }
