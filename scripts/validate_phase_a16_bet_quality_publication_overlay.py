#!/usr/bin/env python3
"""Phase A16 — Bet Quality publication overlay validation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "base44-d"


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    for rel in (
        "worldcup_predictor/publication/bet_quality_overlay.py",
        "worldcup_predictor/publication/__init__.py",
        "worldcup_predictor/predops/combo_readiness.py",
        "worldcup_predictor/predops/public_sanitize.py",
    ):
        record(checks, f"file_{Path(rel).stem}", (ROOT / rel).is_file(), rel)

    fe_files = (
        "src/lib/betQualityOverlay.js",
        "src/lib/comboGenerator.js",
        "src/components/match-center/EliteMatchCard.jsx",
        "src/components/prediction-detail-pro/PredictionSummaryCards.jsx",
    )
    for rel in fe_files:
        record(checks, f"fe_{Path(rel).name}", (FRONTEND / rel).is_file(), rel)

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    scoring = (ROOT / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecision" in wde or "WeightedDecision" in wde)
    record(checks, "scoring_unchanged", "class ScoringEngine" in scoring)

    combo_js = (FRONTEND / "src/lib/comboGenerator.js").read_text(encoding="utf-8")
    record(checks, "combo_no_fixture_no_bet_gate", "s.no_bet" not in combo_js)
    record(checks, "combo_uses_quality", "COMBO_QUALITY_THRESHOLDS" in combo_js)

    elite = (FRONTEND / "src/components/match-center/EliteMatchCard.jsx").read_text(encoding="utf-8")
    record(checks, "ui_no_raw_no_bet", "no_bet" not in elite)
    record(checks, "ui_caution_label", "Caution" in elite and "betQualityFromSummary" in elite)

    try:
        from worldcup_predictor.api.match_center_helpers import extract_prediction_summary
        from worldcup_predictor.publication.bet_quality_overlay import (
            build_publication_overlay,
            compute_market_quality_score,
            quality_tier_from_score,
            sanitize_public_summary,
        )
        from worldcup_predictor.predops.combo_readiness import COMBO_QUALITY_THRESHOLDS, build_combo_readiness_report
        from worldcup_predictor.predops.public_sanitize import sanitize_public_snapshot

        tier = quality_tier_from_score(96)
        record(checks, "tier_elite", tier.get("bet_quality_tier") == "Elite")
        record(checks, "tier_color", tier.get("bet_quality_color") == "dark_green")

        score, inputs, reason = compute_market_quality_score(
            market_key="btts",
            probability=72,
            market_confidence=68,
            fixture_confidence=42,
            data_quality=55,
            ranking_position=0,
            fixture_no_bet=True,
            wde_reasons=["confidence_below_60"],
        )
        record(checks, "quality_formula", score > 0 and "market_probability" in inputs)
        record(checks, "prob_quality_separate", inputs.get("market_probability") != score)

        no_bet_payload = {
            "status": "ok",
            "no_bet": True,
            "prediction": "draw",
            "confidence": 42,
            "data_quality": 52,
            "best_available_pick": {
                "market": "BTTS",
                "pick": "yes",
                "probability": 58,
                "confidence": 58,
            },
            "detailed_markets": {
                "btts": {"selection": "yes", "probability": 58, "confidence": 58},
            },
            "probabilities": {"btts": {"selection": "yes", "probability": 58}},
            "market_ranking": [
                {"market_key": "btts", "pick": "yes", "probability": 58, "confidence": 58},
            ],
            "audit_trace": {"confidence": {"no_bet_reasons": ["confidence_below_60"]}},
        }

        internal = extract_prediction_summary(no_bet_payload)
        record(checks, "wde_no_bet_preserved", internal.get("no_bet") is True)

        overlay = build_publication_overlay(no_bet_payload, include_debug=True)
        record(checks, "caution_status", overlay.get("public_recommendation_status") == "caution_best_available")
        record(checks, "caution_label", overlay.get("caution_label") == "Caution — Best Available")
        record(checks, "derived_flag", overlay.get("derived_from_no_bet_fixture") is True)
        record(checks, "public_best_pick", bool(overlay.get("public_best_pick")))

        enriched = extract_prediction_summary(no_bet_payload)
        record(checks, "summary_has_best_pick", bool(enriched.get("best_pick")))
        record(checks, "summary_caution", enriched.get("display_status") == "caution_best_available")

        public = sanitize_public_summary(enriched)
        record(checks, "public_hides_no_bet", "no_bet" not in public)
        record(checks, "public_has_quality", public.get("bet_quality_score") is not None)

        draw_only = {
            "status": "ok",
            "no_bet": True,
            "prediction": "draw",
            "confidence": 38,
            "detailed_markets": {},
            "probabilities": {},
        }
        draw_summary = extract_prediction_summary(draw_only)
        public_draw = sanitize_public_summary(draw_summary)
        record(
            checks,
            "no_fake_draw_public",
            public_draw.get("best_pick") is None or "draw" not in str(public_draw.get("best_pick", "")).lower(),
        )

        mq = overlay.get("market_quality") or {}
        record(checks, "market_quality_1x2", "1x2" in mq)
        record(checks, "market_quality_btts", "btts" in mq and mq["btts"].get("prediction"))

        unavailable = build_publication_overlay({"status": "ok", "no_bet": True, "detailed_markets": {}})
        um = (unavailable.get("market_quality") or {}).get("1x2", {})
        record(checks, "unavailable_not_faked", um.get("internal_status") == "unavailable")

        owner_overlay = build_publication_overlay(no_bet_payload, include_debug=True)
        record(checks, "owner_wde_reason", bool(owner_overlay.get("wde_no_bet_reasons")))
        public_overlay = build_publication_overlay(no_bet_payload, include_debug=False)
        record(checks, "public_hides_wde_debug", "wde_no_bet_reasons" not in public_overlay)

        record(checks, "combo_thresholds", COMBO_QUALITY_THRESHOLDS.get("safe") == 90.0)
        report = build_combo_readiness_report(matches=[])
        record(checks, "combo_readiness_api", report.get("status") == "ok" and "quality_thresholds" in report)

        snap = sanitize_public_snapshot(
            {
                "snapshot_id": "test",
                "fixture_id": 1,
                "payload": no_bet_payload,
                "markets": {"markets": {"1x2": {"market_status": "no_pick"}}},
            }
        )
        record(checks, "snapshot_overlay", snap and "publication_overlay" in snap)

    except Exception as exc:
        record(checks, "runtime_checks", False, str(exc))

    # Frontend build
    try:
        env = os.environ.copy()
        env.setdefault("CI", "true")
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=300,
            shell=sys.platform == "win32",
            env=env,
        )
        record(checks, "frontend_build", proc.returncode == 0, (proc.stderr or proc.stdout)[-500:])
    except Exception as exc:
        record(checks, "frontend_build", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A16 validation: {passed}/{total} checks passed\n")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail and not ok:
            line += f" — {detail[:200]}"
        print(line)

    out_path = ROOT / "data" / "validation" / "phase_a16_bet_quality_overlay_validation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
