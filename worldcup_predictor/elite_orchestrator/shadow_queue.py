"""Phase A22 — async shadow analysis queue (PredOps hook, non-blocking)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
QUEUE_PATH = ROOT / "data" / "shadow" / "elite_shadow_analysis_queue.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def enqueue_shadow_fixture(
    fixture_id: int,
    *,
    competition_key: str | None = None,
    source: str = "predops_snapshot",
    snapshot_id: str | None = None,
) -> None:
    """Fire-and-forget queue append — never raises to caller."""
    try:
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "queued_at": _utc_now(),
            "fixture_id": int(fixture_id),
            "competition_key": competition_key,
            "source": source,
            "snapshot_id": snapshot_id,
            "status": "queued",
        }
        with QUEUE_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except Exception:
        return


def load_queue(*, limit: int = 500) -> list[dict[str, Any]]:
    if not QUEUE_PATH.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in QUEUE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if row.get("status") == "queued":
                rows.append(row)
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


def mark_queue_processed(fixture_ids: list[int]) -> int:
    if not fixture_ids or not QUEUE_PATH.is_file():
        return 0
    wanted = {int(x) for x in fixture_ids}
    updated = 0
    out_lines: list[str] = []
    for line in QUEUE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            out_lines.append(line)
            continue
        if int(row.get("fixture_id") or 0) in wanted and row.get("status") == "queued":
            row["status"] = "processed"
            row["processed_at"] = _utc_now()
            updated += 1
        out_lines.append(json.dumps(row, default=str))
    QUEUE_PATH.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")
    return updated


def queue_pending_count() -> int:
    return len(load_queue(limit=10000))
