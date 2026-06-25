"""Part A — immutable weight snapshots from 58A recommendations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.elite_self_learning.adaptive_weights import DEFAULT_WEIGHTS
from worldcup_predictor.elite_self_learning.weight_simulation.models import WeightSnapshot

ROOT = Path(__file__).resolve().parents[3]
RECOMMENDATIONS_PATH = ROOT / "data" / "shadow" / "elite_learning_store" / "adaptive_weight_recommendations.json"
ARTIFACT_SNAPSHOT_DIR = ROOT / "artifacts" / "phase58b_self_learning_simulation" / "weight_snapshots"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot_id(market_id: str, label: str, weights: dict[str, float]) -> str:
    payload = json.dumps({"market_id": market_id, "label": label, "weights": weights}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return weights
    return {k: round(v / total, 6) for k, v in weights.items()}


def load_recommendations(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or RECOMMENDATIONS_PATH
    if not p.is_file():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return list(data.get("recommendations") or [])


def build_weight_matrices(recommendations: list[dict[str, Any]]) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    """Return (old_weights, new_weights) per market."""
    old: dict[str, dict[str, float]] = {m: dict(w) for m, w in DEFAULT_WEIGHTS.items()}
    new: dict[str, dict[str, float]] = {m: dict(w) for m, w in DEFAULT_WEIGHTS.items()}

    for rec in recommendations:
        market_id = str(rec.get("market_id") or "")
        cid = str(rec.get("component_id") or "")
        if market_id not in new or not cid:
            continue
        old[market_id][cid] = float(rec.get("current_weight") or new[market_id].get(cid, 0))
        new[market_id][cid] = float(rec.get("recommended_weight") or old[market_id][cid])

    for market_id in new:
        old[market_id] = _normalize(old[market_id])
        new[market_id] = _normalize(new[market_id])
    return old, new


def create_snapshots(
    recommendations: list[dict[str, Any]] | None = None,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    recs = recommendations if recommendations is not None else load_recommendations()
    old_matrices, new_matrices = build_weight_matrices(recs)
    created_at = _utc_now()

    snapshots: list[WeightSnapshot] = []
    for market_id in old_matrices:
        for label, matrix in (("old_weights", old_matrices[market_id]), ("new_weights", new_matrices[market_id])):
            snapshots.append(
                WeightSnapshot(
                    snapshot_id=_snapshot_id(market_id, label, matrix),
                    label=label,
                    market_id=market_id,
                    weights=matrix,
                    source=str(RECOMMENDATIONS_PATH),
                )
            )

    manifest = {
        "generated_at": created_at,
        "phase": "58B",
        "immutable": True,
        "source_recommendations": str(RECOMMENDATIONS_PATH),
        "recommendation_count": len(recs),
        "snapshots": [s.to_dict() for s in snapshots],
        "old_matrices": old_matrices,
        "new_matrices": new_matrices,
    }

    if persist:
        ARTIFACT_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        manifest_path = ARTIFACT_SNAPSHOT_DIR / "snapshots_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        for s in snapshots:
            snap_path = ARTIFACT_SNAPSHOT_DIR / f"{s.market_id}_{s.label}.json"
            snap_path.write_text(json.dumps(s.to_dict(), indent=2), encoding="utf-8")

    return manifest
