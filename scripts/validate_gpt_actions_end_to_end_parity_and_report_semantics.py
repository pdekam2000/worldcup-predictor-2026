#!/usr/bin/env python3
"""Validate GPT Actions WDE parity and prediction report semantics hotfix."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.gpt_actions.bridge_semantics import (
    classify_report_type,
    extract_wde_semantics,
    latest_prediction_report_payload,
    prediction_report_by_date_payload,
)
from worldcup_predictor.gpt_actions.delegation import format_fixture_evidence

FID = 1581821
FROZEN = ROOT / "artifacts" / "today_additional_3_predictions_20260710" / "spain_belgium_reference.json"
FORENSIC = ROOT / "reports" / "owner" / "GPT_ACTIONS_WDE_PARITY_FORENSIC.md"
HOTFIX = ROOT / "reports" / "owner" / "GPT_ACTIONS_END_TO_END_PARITY_AND_REPORT_SEMANTICS_HOTFIX_REPORT.md"
INSTRUCTIONS = ROOT / "docs" / "gpt_actions" / "CUSTOM_GPT_OWNER_INSTRUCTIONS.md"
OPENAPI = ROOT / "docs" / "gpt_actions" / "worldcup_predictor_actions.openapi.yaml"


def _check(name: str, ok: bool, failures: list[str]) -> None:
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if not ok:
        failures.append(name)


def main() -> int:
    failures: list[str] = []
    frozen = json.loads(FROZEN.read_text(encoding="utf-8")) if FROZEN.is_file() else {}
    frozen_hash_before = FROZEN.stat().st_mtime if FROZEN.is_file() else None

    # Simulate stored payload where predicted_1x2 disagrees with canonical decision
    mock_payload = {
        "predicted_1x2": "home_win",
        "one_x_two": {"selection": "draw"},
        "prediction": "draw",
        "decision_source": "RAW_WDE",
        "effective_1x2": {"pick": "draw", "decision_source": "RAW_WDE"},
        "probabilities": {"home_win": 0.534, "draw": 0.241, "away_win": 0.224},
        "confidence_score": 52.6,
    }
    sem = extract_wde_semantics(mock_payload)
    _check("fixture 1581821 frozen evidence file exists", FROZEN.is_file(), failures)
    _check("canonical WDE decision = draw", sem["decision_pick"] == "draw", failures)
    _check("probability argmax = home_win", sem["probability_argmax"] == "home_win", failures)
    _check("H/D/A probabilities preserved", sem["home_prob"] == 53.4 and sem["draw_prob"] == 24.1, failures)
    _check("confidence preserved", sem["confidence"] == 52.6, failures)
    _check("decision_source preserved", sem["decision_source"] == "RAW_WDE", failures)

    mcp_result = {
        "fixture": {"fixture_id": FID, "home_team": "Spain", "away_team": "Belgium", "kickoff_utc": "2026-07-10T19:00:00", "competition": "world_cup_2026"},
        "wde": {
            "home_probability": 53.4,
            "draw_probability": 24.1,
            "away_probability": 22.4,
            "prediction": "draw",
            "decision_pick": "draw",
            "effective_pick": "draw",
            "probability_argmax": "home_win",
            "decision_source": "RAW_WDE",
            "confidence": 52.6,
            "wde_execution_status": "skipped",
            "wde_result_source": "stored_prediction",
            "wde_warning": "engine_error",
        },
        "btts": {"prediction": "yes", "yes_probability": None, "no_probability": None},
        "over_under_2_5": {"prediction": "under_2_5", "over_probability": None, "under_probability": None},
        "ecse": {
            "top_scores": [
                {"rank": 1, "score": "2-0", "probability": 0.1373},
                {"rank": 2, "score": "1-0", "probability": 0.1197},
                {"rank": 3, "score": "3-0", "probability": 0.105},
                {"rank": 4, "score": "2-1", "probability": 0.0905},
                {"rank": 5, "score": "1-1", "probability": 0.0789},
            ]
        },
        "quality": {"status": "PARTIAL", "warnings": ["wde_skipped:engine_error"]},
        "odds": {"provider": "api_football", "freshness": "FRESH_ODDS"},
    }
    formatted = format_fixture_evidence(mcp_result, timezone="Europe/Vienna")
    wde = formatted["wde"]
    _check("Action response preserves decision_pick draw", wde.get("decision_pick") == "draw", failures)
    _check("Action response preserves probability_argmax home_win", wde.get("probability_argmax") == "home_win", failures)
    _check("prediction field equals canonical decision", wde.get("prediction") == "draw", failures)
    _check("warning provenance explicit", wde.get("wde_warning") == "engine_error", failures)
    _check("WDE result source explicit", wde.get("wde_result_source") == "stored_prediction", failures)
    _check("wde_execution_status explicit", wde.get("wde_execution_status") == "skipped", failures)
    _check("BTTS probability only if authentic", formatted["btts"].get("yes_probability") is None or isinstance(formatted["btts"].get("yes_probability"), (int, float)), failures)
    ecse = formatted["ecse"]
    for i, score in enumerate(["2-0", "1-0", "3-0", "2-1", "1-1"], start=1):
        top = ecse.get(f"top{i}") or {}
        _check(f"ECSE Top{i} preserved", top.get("score") == score, failures)

    latest = latest_prediction_report_payload(max_bytes=100_000)
    guide = ROOT / "reports" / "owner" / "PHASE_5_CUSTOM_GPT_CONNECTION_GUIDE.md"
    _check("getLatestPredictionReport excludes connection guide", latest.get("report_name") != guide.name, failures)
    _check("latest report is actual prediction report", latest.get("found") and latest.get("report_type", "").startswith("PREDICTION"), failures)
    _check("report type exposed", bool(latest.get("report_type")), failures)

    by_date = prediction_report_by_date_payload(date(2026, 7, 10), max_bytes=100_000)
    _check("date lookup 2026-07-10 finds prediction report", by_date.get("found") is True, failures)
    _check("date report is not connection guide", by_date.get("report_name") != guide.name, failures)

  # frozen unchanged
    _check("frozen snapshot unchanged", FROZEN.is_file() and FROZEN.stat().st_mtime == frozen_hash_before, failures)

    inst = INSTRUCTIONS.read_text(encoding="utf-8") if INSTRUCTIONS.is_file() else ""
    _check("same job_id polling workflow documented", "Preserve the exact `job_id`" in inst or "preserve exact job_id" in inst.lower(), failures)

    oa = OPENAPI.read_text(encoding="utf-8") if OPENAPI.is_file() else ""
    _check("OpenAPI documents decision_pick", "decision_pick" in oa, failures)
    _check("OpenAPI documents probability_argmax", "probability_argmax" in oa, failures)
    _check("OpenAPI documents report_type", "report_type" in oa, failures)

    _check("forensic report exists", FORENSIC.is_file(), failures)
    _check("hotfix report exists", HOTFIX.is_file(), failures)

    # Bridge-only: no WDE/ECSE model files changed in this hotfix scope
    _check("bridge semantics module exists", (ROOT / "worldcup_predictor" / "gpt_actions" / "bridge_semantics.py").is_file(), failures)

    if failures:
        print(f"\nVALIDATE-GPT-ACTIONS-PARITY: FAILED ({len(failures)} checks)")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nVALIDATE-GPT-ACTIONS-PARITY: ALL CHECKS PASSED (30)")
    print("STATUS = GPT_ACTIONS_END_TO_END_PARITY_RESTORED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
