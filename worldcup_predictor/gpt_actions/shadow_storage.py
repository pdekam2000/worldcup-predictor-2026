"""Tier B shadow prediction storage — owner-only, separate from public surfaces."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.env_loading import project_root

SHADOW_PREDICTIONS_PATH = project_root() / "data" / "shadow" / "tier_b_domestic_predictions.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _payload_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _existing_hashes(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    hashes: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        h = row.get("payload_hash")
        if h:
            hashes.add(str(h))
    return hashes


def freeze_tier_b_shadow_prediction(
    *,
    fixture_id: int,
    competition: str,
    kickoff: str | None,
    odds_timestamp: str | None,
    wde_version: str | None,
    ecse_version: str | None,
    evidence: dict[str, Any],
    path: Path | None = None,
    freeze_id: str | None = None,
    content_hash: str | None = None,
    structured_db_canonical: bool = True,
) -> dict[str, Any]:
    """Append frozen Tier B row if payload hash not already stored (idempotent).

    Structured DB (WSP + ECSE + frozen_predictions) is canonical when
    structured_db_canonical=True. JSONL remains a compatibility audit mirror.
    """
    target = path or SHADOW_PREDICTIONS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    phash = _payload_hash(evidence)
    if phash in _existing_hashes(target):
        return {"stored": False, "reason": "duplicate_payload_hash", "payload_hash": phash}

    row = {
        "prediction_id": str(uuid.uuid4()),
        "fixture_id": int(fixture_id),
        "competition": competition,
        "tier": "B",
        "generated_at": _utc_now(),
        "kickoff": kickoff,
        "odds_timestamp": odds_timestamp,
        "wde_version": wde_version,
        "ecse_version": ecse_version,
        "payload_hash": phash,
        "public_visible": False,
        "owner_visible": True,
        "evaluation_status": "pending",
        "structured_db_canonical": structured_db_canonical,
        "freeze_id": freeze_id,
        "content_hash": content_hash,
        "prediction_scope": "owner_shadow",
        "evidence": evidence,
    }
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"stored": True, "prediction_id": row["prediction_id"], "payload_hash": phash, "path": str(target)}
