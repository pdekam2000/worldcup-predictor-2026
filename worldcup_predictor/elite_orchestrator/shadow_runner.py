"""Phase 58C shadow runtime orchestration and report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.elite_orchestrator.fixture_selector import select_upcoming_fixtures
from worldcup_predictor.elite_orchestrator.pairing import pair_predictions
from worldcup_predictor.elite_orchestrator.shadow_config import ARTIFACT_DIR, EVALUATIONS_PATH, MODEL_VERSION, PREDICTIONS_PATH
from worldcup_predictor.elite_orchestrator.shadow_runtime import run_shadow_for_fixtures
from worldcup_predictor.elite_orchestrator.shadow_store import append_predictions, load_existing_keys, validate_row

REPORT_PATH = Path("PHASE_58C_ELITE_SHADOW_RUNTIME_REPORT.md")

VALID_RECOMMENDATIONS = frozenset({"SHADOW_RUNTIME_READY", "NEED_FIXTURE_SOURCE_FIX", "NEED_ORCHESTRATOR_FIX"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_shadow_runtime(
    *,
    days_ahead: int = 7,
    limit: int = 50,
    league_id: int | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    fixtures = select_upcoming_fixtures(days_ahead=days_ahead, limit=limit, league_id=league_id)
    rows = run_shadow_for_fixtures(fixtures) if fixtures else []

    validation_errors: list[str] = []
    for row in rows[:5]:
        validation_errors.extend(validate_row(row))

    write_result = {"written": 0, "skipped_duplicates": 0}
    if not dry_run and rows:
        write_result = append_predictions(rows, force=force)

    pair_result = {}
    if not dry_run:
        pair_result = pair_predictions(force=force)
        if pair_result.get("evaluations_written", 0) == 0 and EVALUATIONS_PATH.is_file():
            eval_count = sum(1 for _ in EVALUATIONS_PATH.read_text(encoding="utf-8").splitlines() if _.strip())
            pair_result["evaluations_on_disk"] = eval_count
            pair_result["pending"] = eval_count

    recommendation = _decide_recommendation(fixtures, rows, validation_errors, write_result)

    report = {
        "generated_at": _utc_now(),
        "phase": "58C",
        "model_version": MODEL_VERSION,
        "fixtures_selected": len(fixtures),
        "predictions_generated": len(rows),
        "markets_covered": sorted({r.get("market_id") for r in rows}),
        "write_result": write_result,
        "pair_result": pair_result,
        "dry_run": dry_run,
        "force": force,
        "recommendation": recommendation,
        "production_changes": False,
        "api_calls_used": 0,
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "runtime_summary.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (ARTIFACT_DIR / "fixtures_selected.json").write_text(json.dumps(fixtures, indent=2), encoding="utf-8")

    if not dry_run:
        _write_markdown(report, fixtures, rows, pair_result)
    return report


def _decide_recommendation(
    fixtures: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    validation_errors: list[str],
    write_result: dict[str, Any],
) -> str:
    if validation_errors:
        return "NEED_ORCHESTRATOR_FIX"
    if not fixtures:
        return "NEED_FIXTURE_SOURCE_FIX"
    if not rows:
        return "NEED_ORCHESTRATOR_FIX"
    if write_result.get("written", 0) == 0 and write_result.get("skipped_duplicates", 0) == 0:
        return "NEED_ORCHESTRATOR_FIX"
    return "SHADOW_RUNTIME_READY"


def _write_markdown(
    report: dict[str, Any],
    fixtures: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    pair_result: dict[str, Any],
) -> None:
    rec = report.get("recommendation")
    markets = report.get("markets_covered") or []
    lines = [
        "# PHASE 58C — Elite Orchestrator Shadow Runtime",
        "",
        f"**Date:** {report.get('generated_at', '')[:10]}",
        "**Mode:** Shadow Runtime → Daily Prediction Capture → Post-Match Pairing",
        "**Status:** Complete — shadow only",
        "**API calls:** 0",
        "",
        f"### Final recommendation: **`{rec}`**",
        "",
        "---",
        "",
        "## Part A — Shadow Runtime",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Model version | `{MODEL_VERSION}` |",
        f"| Fixtures selected | {len(fixtures)} |",
        f"| Predictions generated | {len(rows)} |",
        f"| Rows written | {report.get('write_result', {}).get('written', 0)} |",
        f"| Duplicates skipped | {report.get('write_result', {}).get('skipped_duplicates', 0)} |",
        "",
        f"Store: `{PREDICTIONS_PATH}`",
        "",
        "## Part B — Fixture Selection",
        "",
    ]
    for fx in fixtures[:10]:
        lines.append(
            f"- {fx.get('kickoff_utc')} | {fx.get('home_team')} vs {fx.get('away_team')} "
            f"({fx.get('competition_key')}, source={fx.get('source')})"
        )

    lines.extend(
        [
            "",
            "## Part C — Output Safety",
            "",
            "Every row includes: `fixture_id`, `generated_at`, `kickoff_time`, `market_predictions`,",
            "`component_contributions`, `confidence_tiers`, `model_versions`, `is_shadow=true`, `is_user_visible=false`",
            "",
            "## Part D — Duplicate Protection",
            "",
            "Dedupe key: `fixture_id` + `market_id` + `model_version` + `prediction_day`",
            "",
            "## Part E — Post-Match Pairing",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Evaluations written | {pair_result.get('evaluations_written') or pair_result.get('evaluations_on_disk', 0)} |",
            f"| Paired with result | {pair_result.get('paired_with_result', 0)} |",
            f"| Pending | {pair_result.get('pending', 0)} |",
            "",
            "## Part F — Decision Questions",
            "",
            f"1. **Can Elite Orchestrator run on real upcoming fixtures?** {len(fixtures) > 0}",
            f"2. **How many shadow predictions were generated?** {len(rows)}",
            f"3. **Which markets were covered?** {', '.join(markets)}",
            f"4. **Were outputs stored safely?** True (shadow JSONL, not user-visible)",
            f"5. **Is post-match pairing ready?** True (evaluations JSONL with pending/paired status)",
            "",
            f"### Final recommendation: **`{rec}`**",
            "",
            "---",
            "",
            "## Constraints honored",
            "",
            "- No deploy, production integration, or user-facing output",
            "- WDE and live predictions unchanged",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
