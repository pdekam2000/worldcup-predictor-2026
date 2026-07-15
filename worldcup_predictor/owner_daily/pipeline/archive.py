"""Append-only daily report archive index."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.owner_daily.pipeline.constants import REPORT_INDEX_PATH


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def append_report_index(
    *,
    report_date: str,
    pipeline_status: str,
    stats: dict[str, Any],
    report_paths: dict[str, str],
) -> Path:
    REPORT_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, Any]] = []
    if REPORT_INDEX_PATH.exists():
        try:
            index = json.loads(REPORT_INDEX_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            index = []
    if not isinstance(index, list):
        index = []

    entry = {
        "report_date": report_date,
        "report_type": "daily_pipeline",
        "generated_at_utc": _utc_now(),
        "timezone": "Europe/Vienna",
        "discovered_count": stats.get("discovered"),
        "predicted_count": stats.get("eligible"),
        "frozen_count": stats.get("frozen"),
        "evaluated_count": stats.get("evaluated"),
        "wde_hits": stats.get("wde_hits"),
        "top5_hits": stats.get("top5_hits"),
        "pipeline_status": pipeline_status,
        "report_paths": report_paths,
        "version": 1,
    }
    # Replace same-date entry (version bump) rather than silent overwrite of eval content
    replaced = False
    for i, row in enumerate(index):
        if row.get("report_date") == report_date and row.get("report_type") == "daily_pipeline":
            entry["version"] = int(row.get("version") or 1) + 1
            index[i] = entry
            replaced = True
            break
    if not replaced:
        index.append(entry)
    index.sort(key=lambda x: str(x.get("report_date") or ""), reverse=True)
    REPORT_INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return REPORT_INDEX_PATH
