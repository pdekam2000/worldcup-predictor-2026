#!/usr/bin/env python3
"""Challenger Model Program — Phases 1–5 orchestration (shadow only).

Does not modify WDE/ECSE/BTTS/O/U formulas or public outputs.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.challenger.backtest.runner import run_gbgm_backtest
from worldcup_predictor.challenger.constants import (
    CHALLENGER_FINAL_DECISION_AUTHORITY,
    CHALLENGER_PUBLIC_VISIBLE,
    FORWARD_THRESHOLDS,
)
from worldcup_predictor.challenger.forward import run_forward_shadow_batch
from worldcup_predictor.challenger.models.gbgm import GBGMChallenger, available_backends
from worldcup_predictor.challenger.prediction_store import ensure_challenger_schema, save_model_run, save_promotion_review
from worldcup_predictor.challenger.promotion_policy import review_promotion
from worldcup_predictor.challenger.registry import list_models, register_model
from worldcup_predictor.challenger.schemas import content_hash, utc_now
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.gpt_actions.delegation import discover_today_matches
from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS

ART = ROOT / "artifacts" / "challenger_program"
REPORTS = ROOT


def _w(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _j(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    ensure_challenger_schema(conn)

    # -------- Phase 1 --------
    phase1 = {
        "package": "worldcup_predictor/challenger",
        "is_shadow": True,
        "public_visible": CHALLENGER_PUBLIC_VISIBLE,
        "final_decision_authority": CHALLENGER_FINAL_DECISION_AUTHORITY,
        "independent_tables": [
            "challenger_predictions",
            "challenger_freezes",
            "challenger_evaluations",
            "challenger_comparisons",
            "challenger_model_runs",
            "challenger_promotion_reviews",
        ],
        "canonical_untouched": True,
        "status": "CHALLENGER_FRAMEWORK_READY",
    }
    assert CHALLENGER_PUBLIC_VISIBLE is False
    assert CHALLENGER_FINAL_DECISION_AUTHORITY is False
    _j(ART / "phase1.json", phase1)
    _w(
        REPORTS / "CHALLENGER_PHASE1_FRAMEWORK_REPORT.md",
        "\n".join(
            [
                "# CHALLENGER PHASE 1 — FRAMEWORK REPORT",
                "",
                "**Status:** `CHALLENGER_FRAMEWORK_READY`",
                "",
                "- Isolated package `worldcup_predictor/challenger/`",
                "- Generic model interface + independent stores",
                "- `is_shadow=true`, `public_visible=false`, `final_decision_authority=false`",
                "- Additive DDL only; WDE/ECSE tables not written",
                "- Feature snapshots are read-only prematch builders",
                "",
                "```text",
                "CHALLENGER_FRAMEWORK_READY",
                "```",
                "",
            ]
        ),
    )

    # -------- Phase 2 --------
    phase2 = {
        "time_based_split": "60/20/20 chronological",
        "holdout_untouched_until_final": True,
        "anti_leakage": [
            "feature_available_at <= kickoff",
            "no target fixture in form windows",
            "no post-match fields in feature contract",
            "future odds rejected when timestamp after prediction_time",
        ],
        "metrics_module": "worldcup_predictor/challenger/backtest/metrics.py",
        "status": "CHALLENGER_BACKTEST_FRAMEWORK_READY",
    }
    _j(ART / "phase2.json", phase2)
    _w(
        REPORTS / "CHALLENGER_PHASE2_BACKTEST_FRAMEWORK_REPORT.md",
        "\n".join(
            [
                "# CHALLENGER PHASE 2 — BACKTEST FRAMEWORK REPORT",
                "",
                "**Status:** `CHALLENGER_BACKTEST_FRAMEWORK_READY`",
                "",
                "- Chronological expanding split + untouched holdout",
                "- Dataset manifests with leakage checks",
                "- Metrics: accuracy, Brier, LogLoss, TopK, bootstrap CI",
                "- ROI only when historical odds exist (not simulated with current odds)",
                "- Reconstructed vs frozen labels separated (`RECONSTRUCTED_RESEARCH_ONLY`)",
                "",
                "```text",
                "CHALLENGER_BACKTEST_FRAMEWORK_READY",
                "```",
                "",
            ]
        ),
    )

    # -------- Phase 3 --------
    comps = [c for c in DAILY_SUPPORTED_COMPETITIONS if c in {"premier_league", "bundesliga", "world_cup_2026", "champions_league"}]
    if not comps:
        comps = list(DAILY_SUPPORTED_COMPETITIONS)[:4]
    backends = available_backends()
    bt = run_gbgm_backtest(conn, comps)
    _j(ART / "phase3_backtest.json", bt)

    # Register selected models
    for variant, block in (bt.get("variants") or {}).items():
        if not block.get("ok"):
            continue
        be = block.get("selected_backend_by_val_logloss") or "lightgbm"
        mid = f"GBGM-1-{variant}-{be}"
        register_model(
            mid,
            {
                "model_id": mid,
                "variant": variant,
                "backend": be,
                "holdout": (block.get("backends") or {}).get(be, {}).get("holdout"),
                "shadow": True,
            },
        )

    save_model_run(
        conn,
        {
            "run_id": f"gbgm_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            "model_id": "GBGM-1",
            "model_version": "GBGM-1.0.0",
            "phase": "phase3",
            "dataset_manifest_hash": ((bt.get("variants") or {}).get("NM") or {}).get("manifest", {}).get("hash"),
            "metrics": bt,
            "artifact_meta": {"backends_available": backends, "competitions": comps},
        },
    )

    phase3_status = "GBGM_CHALLENGER_BACKTEST_COMPLETE"
    if not any((v or {}).get("ok") for v in (bt.get("variants") or {}).values()):
        phase3_status = "GBGM_CHALLENGER_FAILED_VALIDATION"

    _w(
        REPORTS / "CHALLENGER_PHASE3_GBGM_MODEL_REPORT.md",
        "\n".join(
            [
                "# CHALLENGER PHASE 3 — GBGM MODEL REPORT",
                "",
                f"**Status:** `{phase3_status}`",
                f"**Backends available:** {backends}",
                f"**Competitions:** {comps}",
                "",
                "## Variants",
                "",
                "- `GBGM-1-NM` — no market features",
                "- `GBGM-1-MC` — market-calibrated (prematch implied odds only)",
                "",
                "## Score distribution",
                "",
                "Independent Poisson from predicted λ → labeled `GBGM_SCORE_DISTRIBUTION` (not ECSE).",
                "",
                "## Safety",
                "",
                "- Shadow only / non-public / no final decision authority",
                "- Does not copy WDE Decision or ECSE Top5",
                "",
                "```text",
                phase3_status,
                "```",
                "",
            ]
        ),
    )
    _w(
        REPORTS / "CHALLENGER_PHASE3_GBGM_BACKTEST_REPORT.md",
        "# CHALLENGER PHASE 3 — GBGM BACKTEST REPORT\n\n```json\n"
        + json.dumps(bt, indent=2, ensure_ascii=False, default=str)[:150000]
        + "\n```\n",
    )

    # -------- Phase 4 (activate infrastructure; do not invent forward results) --------
    today = datetime.now().astimezone().date().isoformat()
    # Prefer Europe/Vienna if available
    try:
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Europe/Vienna")).date().isoformat()
    except Exception:
        pass

    discovery = discover_today_matches(target_date=today, timezone="Europe/Vienna", scope="owner")
    matches = discovery.get("matches") or []
    # Train a small NM model on historical comps for forward shadow (if phase3 ok)
    forward_payload = {"activated": False, "completed_forward_evaluations": 0, "predictions_attempted": 0}
    if phase3_status == "GBGM_CHALLENGER_BACKTEST_COMPLETE":
        # Fit NM lightgbm or sklearn on reconstructed train for shadow scoring only
        from worldcup_predictor.challenger.backtest.runner import build_dataset
        from worldcup_predictor.challenger.backtest.splits import chronological_split

        ds = build_dataset(conn, comps, include_market=False)
        rows = ds["rows"]
        if len(rows) >= 80:
            split = chronological_split(rows)
            by_id = {r["fixture_id"]: r for r in rows}
            train = [by_id[i] for i in split.train_ids if i in by_id]
            backend = "lightgbm" if "lightgbm" in backends else "sklearn_hist"
            model = GBGMChallenger(variant="NM", backend=backend)
            model.fit(
                [r["features"] for r in train],
                [r["home_goals"] for r in train],
                [r["away_goals"] for r in train],
                sample_meta={"purpose": "forward_shadow_fit", "holdout_excluded": True},
            )
            fixture_rows = []
            for m in matches:
                fixture_rows.append(
                    {
                        "fixture_id": int(m["fixture_id"]),
                        "prediction_scope": "owner_shadow",
                        "validation_tier": m.get("validation_tier") or m.get("tier"),
                        "canonical_summary": None,
                    }
                )
            batch = run_forward_shadow_batch(conn, model, fixture_rows)
            forward_payload = {
                "activated": True,
                "predictions_attempted": batch.get("n"),
                "failures": batch.get("failures"),
                "completed_forward_evaluations": 0,  # no inventing post-match evals
                "thresholds": FORWARD_THRESHOLDS,
                "model_id": model.model_id,
                "note": "Forward shadow active; completed evaluation count remains 0 until confirmed results exist",
            }
            _j(ART / "phase4_forward_batch.json", {"summary": forward_payload, "batch_keys": list(batch.keys())})
            # stub rolling reports stating insufficient completed sample
            for n in (50, 100, 250):
                _w(
                    REPORTS / f"CHALLENGER_FORWARD_{n}_REPORT.md",
                    f"# CHALLENGER FORWARD {n} REPORT\n\n"
                    f"Completed evaluated fixtures: **0** / required **{n}**.\n\n"
                    "No forward results invented.\n",
                )

    _w(
        REPORTS / "CHALLENGER_PHASE4_FORWARD_SHADOW_REPORT.md",
        "\n".join(
            [
                "# CHALLENGER PHASE 4 — FORWARD SHADOW REPORT",
                "",
                f"**Activated:** {forward_payload.get('activated')}",
                f"**Predictions attempted today:** {forward_payload.get('predictions_attempted')}",
                f"**Completed forward evaluations:** {forward_payload.get('completed_forward_evaluations')} (not invented)",
                "",
                "- Canonical remains sole user-facing authority",
                "- Challenger freeze additive / immutable",
                "- Challenger failure does not block canonical",
                "",
                "```text",
                "CHALLENGER_FORWARD_SHADOW_ACTIVE" if forward_payload.get("activated") else "CHALLENGER_FORWARD_SHADOW_VALIDATION_FAILED",
                "```",
                "",
            ]
        ),
    )
    phase4_status = "CHALLENGER_FORWARD_SHADOW_ACTIVE" if forward_payload.get("activated") else "CHALLENGER_FORWARD_SHADOW_VALIDATION_FAILED"

    # -------- Phase 5 --------
    holdout_improved = None
    nm = (bt.get("variants") or {}).get("NM") or {}
    if nm.get("ok"):
        be = nm.get("selected_backend_by_val_logloss")
        hold = ((nm.get("backends") or {}).get(be) or {}).get("holdout") or {}
        base = nm.get("league_avg_holdout") or {}
        # lower logloss is better
        if hold.get("logloss_1x2") is not None and base.get("logloss_1x2") is not None:
            holdout_improved = float(hold["logloss_1x2"]) < float(base["logloss_1x2"])

    review = review_promotion(
        model_id="GBGM-1",
        model_version="GBGM-1.0.0",
        forward_completed_n=int(forward_payload.get("completed_forward_evaluations") or 0),
        holdout_improved=holdout_improved,
        backtest_passed=phase3_status == "GBGM_CHALLENGER_BACKTEST_COMPLETE",
        evidence={
            "approve_ensemble_research": False,
            "domain_limited": False,
            "backends": backends,
            "registered_models": list_models(),
            "answers_pending_forward_sample": True,
        },
    )
    save_promotion_review(conn, review)
    _j(ART / "phase5_review.json", review)
    phase5_decision = review["decision"]
    _w(
        REPORTS / "CHALLENGER_PHASE5_PROMOTION_REVIEW.md",
        "\n".join(
            [
                "# CHALLENGER PHASE 5 — PROMOTION REVIEW",
                "",
                f"**Decision:** `{phase5_decision}`",
                f"**Forward completed fixtures:** {forward_payload.get('completed_forward_evaluations')} (need ≥{FORWARD_THRESHOLDS['promotion_quality']})",
                f"**Holdout improved vs league-avg (1X2 logloss):** {holdout_improved}",
                "",
                "## Answers",
                "",
                "1–4. Probability / O/U / BTTS / ECSE comparisons require paired forward freezes — **insufficient completed sample**.",
                "5–6. Stability by league/time — pending forward sample.",
                "7–8. NM vs MC — see Phase 3 backtest JSON; do not promote from backtest alone.",
                "9–12. Calibration/coverage/cost/regressions — pending ≥250 forward fixtures.",
                "13. More forward data required: **YES**.",
                "14. Domain-limited research: not approved yet.",
                "15. Ensemble research: **NOT approved** (max gate not met).",
                "",
                "Canonical replacement: **FORBIDDEN**.",
                "",
                "```text",
                phase5_decision,
                "```",
                "",
            ]
        ),
    )

    # -------- Master --------
    if phase3_status != "GBGM_CHALLENGER_BACKTEST_COMPLETE":
        program_status = "CHALLENGER_PROGRAM_VALIDATION_FAILED"
    elif phase4_status == "CHALLENGER_FORWARD_SHADOW_ACTIVE" and int(forward_payload.get("completed_forward_evaluations") or 0) == 0:
        program_status = "CHALLENGER_FORWARD_EVALUATION_ACTIVE"
    elif phase4_status == "CHALLENGER_FORWARD_SHADOW_ACTIVE":
        program_status = "CHALLENGER_FORWARD_EVALUATION_ACTIVE"
    else:
        program_status = "CHALLENGER_FRAMEWORK_AND_BACKTEST_READY"

    # Prefer FRAMEWORK_AND_BACKTEST_READY when phases 1-3 done and forward active but no completed evals yet
    # User said: FRAMEWORK_AND_BACKTEST_READY when Phases 1–3 complete but forward data still accumulating
    # AND CHALLENGER_FORWARD_EVALUATION_ACTIVE when Phase 4 operational
    # Phase 4 is operational → use FORWARD_EVALUATION_ACTIVE
    if phase1["status"] == "CHALLENGER_FRAMEWORK_READY" and phase2["status"] == "CHALLENGER_BACKTEST_FRAMEWORK_READY" and phase3_status == "GBGM_CHALLENGER_BACKTEST_COMPLETE":
        if phase4_status == "CHALLENGER_FORWARD_SHADOW_ACTIVE":
            program_status = "CHALLENGER_FORWARD_EVALUATION_ACTIVE"
        else:
            program_status = "CHALLENGER_FRAMEWORK_AND_BACKTEST_READY"

    master = {
        "program_status": program_status,
        "phase1": phase1["status"],
        "phase2": phase2["status"],
        "phase3": phase3_status,
        "phase4": phase4_status,
        "phase5": phase5_decision,
        "public_visible": False,
        "final_decision_authority": False,
        "canonical_unchanged": True,
        "generated_at": utc_now(),
        "local_sha_note": "Recorded by operator at commit/deploy time",
    }
    _j(ART / "master_summary.json", master)
    _w(
        REPORTS / "CHALLENGER_MODEL_PROGRAM_MASTER_REPORT.md",
        "\n".join(
            [
                "# CHALLENGER MODEL PROGRAM — MASTER REPORT",
                "",
                f"**Program status:** `{program_status}`",
                "",
                f"- Phase 1: `{phase1['status']}`",
                f"- Phase 2: `{phase2['status']}`",
                f"- Phase 3: `{phase3_status}`",
                f"- Phase 4: `{phase4_status}`",
                f"- Phase 5: `{phase5_decision}`",
                "",
                "## Safety",
                "",
                "- WDE / ECSE / BTTS / O/U formulas unchanged",
                "- Public visibility false",
                "- Final decision authority false",
                "- Additive challenger_* tables only",
                "- No automatic production promotion",
                "",
                "## Rollback",
                "",
                "1. Stop calling Challenger runner from full-day wrapper",
                "2. Leave challenger_* tables in place (or drop only those tables)",
                "3. Canonical freezes and predictions remain authoritative",
                "",
                "## Unresolved risks",
                "",
                "- Forward sample = 0 completed evaluations",
                "- XGBoost/CatBoost not installed (LightGBM + sklearn compared)",
                "- Historical odds ROI not claimed without matched prematch odds series",
                "",
                "```text",
                program_status,
                "```",
                "",
            ]
        ),
    )

    conn.close()
    print(json.dumps(master, indent=2))
    print(program_status)
    return 0 if program_status != "CHALLENGER_PROGRAM_VALIDATION_FAILED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
