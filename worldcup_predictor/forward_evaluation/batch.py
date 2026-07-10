"""Phase 7B Part G — Daily batch manifest."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.forward_evaluation.constants import ARTIFACTS_DIR, BATCH_PREFIX, DEFAULT_TIMEZONE


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def batch_id_for(date_str: str) -> str:
    compact = date_str.replace("-", "")
    return f"{BATCH_PREFIX}_{compact}"


def write_batch_manifest(
    *,
    evaluation_date: str,
    timezone: str,
    discovered: list[dict[str, Any]],
    eligible: list[dict[str, Any]],
    excluded: list[dict[str, Any]],
    frozen: list[dict[str, Any]],
    evaluated: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest = {
        "batch_id": batch_id_for(evaluation_date),
        "date": evaluation_date,
        "timezone": timezone,
        "created_at": _utc_now(),
        "discovered_count": len(discovered),
        "eligible_count": len(eligible),
        "predicted_count": len(frozen),
        "frozen_count": len(frozen),
        "excluded_count": len(excluded),
        "evaluated_count": len(evaluated),
        "fixture_ids": [int(f["fixture_id"]) for f in frozen],
        "prediction_ids": [f.get("prediction_id") for f in frozen if f.get("prediction_id")],
        "excluded": excluded,
    }
    blob = json.dumps(manifest, sort_keys=True, default=str)
    manifest["batch_hash"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    out_dir = (project_root() / ARTIFACTS_DIR / evaluation_date.replace("-", "")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "batch_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(path)
    return manifest


def upsert_batch_record(eval_conn: sqlite3.Connection, manifest: dict[str, Any]) -> None:
    eval_conn.execute(
        """
        INSERT INTO evaluation_batches (
            batch_id, evaluation_date, timezone, created_at, discovered_count, eligible_count,
            frozen_count, excluded_count, evaluated_count, status, batch_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(batch_id) DO UPDATE SET
            discovered_count=excluded.discovered_count,
            eligible_count=excluded.eligible_count,
            frozen_count=excluded.frozen_count,
            excluded_count=excluded.excluded_count,
            evaluated_count=excluded.evaluated_count,
            status=excluded.status,
            batch_hash=excluded.batch_hash
        """,
        (
            manifest["batch_id"],
            manifest["date"],
            manifest.get("timezone") or DEFAULT_TIMEZONE,
            manifest.get("created_at") or _utc_now(),
            manifest.get("discovered_count") or 0,
            manifest.get("eligible_count") or 0,
            manifest.get("frozen_count") or 0,
            manifest.get("excluded_count") or 0,
            manifest.get("evaluated_count") or 0,
            "complete",
            manifest.get("batch_hash"),
        ),
    )
    eval_conn.commit()


def store_excluded(
    eval_conn: sqlite3.Connection,
    *,
    batch_id: str,
    fixture: dict[str, Any],
    reason: str,
    detail: dict[str, Any],
) -> None:
    eval_conn.execute(
        """
        INSERT OR REPLACE INTO excluded_candidates (
            batch_id, fixture_id, match_name, competition, tier, kickoff, exclusion_reason, detail_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            int(fixture["fixture_id"]),
            f"{fixture.get('home_team')} vs {fixture.get('away_team')}",
            fixture.get("competition"),
            fixture.get("tier"),
            fixture.get("kickoff_utc") or fixture.get("kickoff"),
            reason,
            json.dumps(detail, default=str),
        ),
    )
    eval_conn.commit()
