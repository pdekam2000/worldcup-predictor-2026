"""PHASE ECSE-X3-B — Append-only owner shadow lab storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_x3_b.constants import CANDIDATE_ID, METHOD_VERSION, SHADOW_ARTIFACT


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _artifact_path(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        root = Path(__file__).resolve().parents[3]
        p = root / p
    return p


def row_key(row: dict[str, Any]) -> str:
    return f"{row.get('fixture_id')}|{row.get('odds_snapshot_id') or 'na'}|{row.get('x3_candidate') or CANDIDATE_ID}"


def append_owner_shadow_row(
    payload: dict[str, Any],
    *,
    artifact_path: str | Path = SHADOW_ARTIFACT,
) -> tuple[bool, str]:
    path = _artifact_path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    existing.add(row_key(json.loads(line)))
                except json.JSONDecodeError:
                    continue
    row = {
        **payload,
        "timestamp": payload.get("timestamp") or _utc_now(),
        "x3_candidate": payload.get("x3_candidate") or CANDIDATE_ID,
        "method_version": payload.get("method_version") or METHOD_VERSION,
        "public_prediction_changed": False,
    }
    key = row_key(row)
    if key in existing:
        return False, "duplicate"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return True, "appended"


def read_owner_shadow_rows(
    *,
    artifact_path: str | Path = SHADOW_ARTIFACT,
    limit: int = 50_000,
) -> list[dict[str, Any]]:
    path = _artifact_path(artifact_path)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    rows.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    return rows[:limit]


def get_owner_shadow_for_fixture(
    fixture_id: int,
    *,
    artifact_path: str | Path = SHADOW_ARTIFACT,
) -> dict[str, Any] | None:
    for row in read_owner_shadow_rows(artifact_path=artifact_path, limit=50_000):
        if int(row.get("fixture_id") or 0) == int(fixture_id):
            return row
    return None
