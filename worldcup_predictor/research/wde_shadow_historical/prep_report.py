"""Part D — WDE shadow retrain preparation report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.research.wde_shadow_historical.constants import (
    DATASET_PATH,
    DATASET_SUMMARY,
    MIN_SHADOW_TRAINING_ROWS,
    PHASE,
    PREP_REPORT,
    READINESS_ARTIFACT,
    READINESS_REPORT,
)


def derive_prep_recommendation(
    *,
    readiness: dict[str, Any],
    build: dict[str, Any],
    validation: dict[str, Any] | None,
) -> str:
    status = str(readiness.get("readiness") or "DO_NOT_TRAIN_YET")
    usable = int((readiness.get("usable_rows") or {}).get("wde_1x2") or 0)

    if status == "DO_NOT_TRAIN_YET" or usable < 1_000:
        return "DO_NOT_TRAIN_YET"
    if readiness.get("missing_teams", 0) > 0 or status == "NEED_TEAM_ALIAS_MAPPING":
        if build.get("row_count", 0) >= MIN_SHADOW_TRAINING_ROWS and validation and validation.get("passed"):
            return "READY_FOR_WDE_SHADOW_TRAINING"
        return "NEED_TEAM_ALIAS_MAPPING_FIRST"
    if status == "NEED_LEAGUE_MAPPING":
        if build.get("row_count", 0) >= MIN_SHADOW_TRAINING_ROWS:
            return "READY_FOR_WDE_SHADOW_TRAINING"
        return "NEED_LEAGUE_MAPPING_FIRST"
    if status == "NEED_DATA_CLEANING":
        return "NEED_DATA_CLEANING_FIRST"
    if build.get("skipped_reason"):
        if usable < MIN_SHADOW_TRAINING_ROWS:
            return "INSUFFICIENT_TRAINING_ROWS"
        return "DO_NOT_TRAIN_YET"
    if validation and not validation.get("passed"):
        return "NEED_DATA_CLEANING_FIRST"
    if build.get("row_count", 0) < MIN_SHADOW_TRAINING_ROWS:
        return "INSUFFICIENT_TRAINING_ROWS"
    if validation and validation.get("passed"):
        return "READY_FOR_WDE_SHADOW_TRAINING"
    return "DO_NOT_TRAIN_YET"


def write_prep_report(
    *,
    recommendation: str,
    readiness: dict[str, Any] | None = None,
    build: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
) -> Path:
    readiness = readiness or _load_json(READINESS_ARTIFACT)
    build = build or _load_json(DATASET_SUMMARY)
    validation = validation or {}

    lines = [
        "# WDE Shadow Retrain Preparation Report",
        "",
        f"**Phase:** {PHASE}",
        f"**Recommendation:** `{recommendation}`",
        "",
        "## Readiness status",
        "",
        f"- Readiness: **{readiness.get('readiness', 'unknown')}**",
        f"- Staged match rows: **{readiness.get('staged_match_rows', 0):,}**",
        f"- Staged odds rows: **{readiness.get('staged_odds_rows', 0):,}**",
        f"- Usable WDE 1X2 rows: **{(readiness.get('usable_rows') or {}).get('wde_1x2', 0):,}**",
        "",
        "## Usable row counts",
        "",
    ]
    for key, val in sorted((readiness.get("usable_rows") or {}).items()):
        lines.append(f"- {key}: **{val:,}**")

    lines.extend(["", "## Blockers", ""])
    blockers = readiness.get("blockers") or []
    if blockers:
        for b in blockers:
            lines.append(f"- {b}")
    else:
        lines.append("- None listed")

    lines.extend(
        [
            "",
            "## Shadow dataset",
            "",
            f"- Built: **{'yes' if DATASET_PATH.exists() else 'no'}**",
            f"- Path: `{DATASET_PATH}`" if DATASET_PATH.exists() else "- Path: not created",
            f"- Rows: **{build.get('row_count', 0):,}**",
            f"- Skipped reason: {build.get('skipped_reason') or 'none'}",
            "",
            "## Validation",
            "",
            f"- Passed: **{validation.get('passed', False)}**",
            f"- Checks: {sum(1 for c in validation.get('checks', []) if c.get('passed'))}/{len(validation.get('checks', []))}",
            "",
            "## Safe to proceed to shadow training?",
            "",
        ]
    )

    if recommendation == "READY_FOR_WDE_SHADOW_TRAINING":
        lines.append("**Yes** — canonical shadow dataset validated; production WDE unchanged.")
    else:
        lines.append(f"**Not yet** — resolve `{recommendation}` before shadow training.")

    lines.extend(
        [
            "",
            "## Constraints",
            "",
            "- Owner/internal research only",
            "- No production WDE replacement",
            "- No writes to worldcup_stored_predictions or odds_snapshots",
            "- Staging tables only as source",
            "",
            f"Readiness report: `{READINESS_REPORT}`",
            f"Readiness artifact: `{READINESS_ARTIFACT}`",
        ]
    )

    PREP_REPORT.write_text("\n".join(lines), encoding="utf-8")
    return PREP_REPORT


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
