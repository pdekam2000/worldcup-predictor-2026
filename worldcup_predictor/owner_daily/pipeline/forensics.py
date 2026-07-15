"""Structured forensic records from daily evaluation misses."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.owner_daily.pipeline.constants import FORENSICS_DIR


def write_forensic_records(
    report_date: str,
    eligibility: list[dict[str, Any]],
    pred_by_fixture: dict[int, dict[str, Any]],
    *,
    settings: Settings | None = None,
) -> Path | None:
    settings = settings or get_settings()
    FORENSICS_DIR.mkdir(parents=True, exist_ok=True)
    path = FORENSICS_DIR / f"daily_forensics_{report_date.replace('-', '')}.jsonl"
    records: list[dict[str, Any]] = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    for row in eligibility:
        if row.get("eligible"):
            continue
        records.append(
            {
                "recorded_at_utc": ts,
                "report_date": report_date,
                "fixture_id": row.get("fixture_id"),
                "match": row.get("match"),
                "category": "blocked_fixture",
                "lifecycle_status": row.get("lifecycle_status"),
                "reason": row.get("eligibility_reason"),
            }
        )

    for fid, pred in pred_by_fixture.items():
        freeze = pred.get("freeze") or {}
        if freeze.get("quarantined"):
            records.append(
                {
                    "recorded_at_utc": ts,
                    "report_date": report_date,
                    "fixture_id": fid,
                    "category": "freeze_quarantine",
                    "reason_code": freeze.get("reason_code"),
                }
            )

    if not records:
        return None
    with path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path
