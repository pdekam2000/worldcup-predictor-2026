"""PHASE ECSE-X2-M6 — Append-only shadow-live JSONL storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_x2_m6.constants import EVAL_ARTIFACT, METHOD_VERSION, SHADOW_ARTIFACT


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _artifact_path(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        root = Path(__file__).resolve().parents[3]
        p = root / p
    return p


def _load_keys(path: Path, *, key_fn) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            keys.add(key_fn(row))
        except json.JSONDecodeError:
            continue
    return keys


def shadow_row_key(row: dict[str, Any]) -> str:
    return f"{row.get('fixture_id')}|{row.get('odds_snapshot_id') or 'na'}|{row.get('method_version')}"


def append_shadow_shortlist(
    payload: dict[str, Any],
    *,
    artifact_path: str | Path = SHADOW_ARTIFACT,
) -> tuple[bool, str]:
    path = _artifact_path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_keys(path, key_fn=shadow_row_key)
    row = {
        **payload,
        "generated_at": payload.get("generated_at") or _utc_now(),
        "method_version": payload.get("method_version") or METHOD_VERSION,
        "public_output_changed": False,
        "evaluation_status": payload.get("evaluation_status") or "pending",
    }
    key = shadow_row_key(row)
    if key in existing:
        return False, "duplicate"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return True, "appended"


def eval_row_key(row: dict[str, Any]) -> str:
    return f"{row.get('fixture_id')}|{row.get('snapshot_id') or 'na'}|{row.get('method_version')}"


def append_shadow_evaluation(
    payload: dict[str, Any],
    *,
    artifact_path: str | Path = EVAL_ARTIFACT,
) -> tuple[bool, str]:
    path = _artifact_path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_keys(path, key_fn=eval_row_key)
    row = {
        **payload,
        "evaluated_at": payload.get("evaluated_at") or _utc_now(),
        "method_version": payload.get("method_version") or METHOD_VERSION,
    }
    key = eval_row_key(row)
    if key in existing:
        return False, "duplicate"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return True, "appended"


def read_shadow_shortlists(
    *,
    artifact_path: str | Path = SHADOW_ARTIFACT,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    path = _artifact_path(artifact_path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    rows.sort(key=lambda r: r.get("generated_at") or "", reverse=True)
    return rows[offset : offset + limit]


def get_shadow_shortlist_for_fixture(
    fixture_id: int,
    *,
    artifact_path: str | Path = SHADOW_ARTIFACT,
) -> dict[str, Any] | None:
    for row in read_shadow_shortlists(artifact_path=artifact_path, limit=10_000):
        if int(row.get("fixture_id") or 0) == int(fixture_id):
            return row
    return None
