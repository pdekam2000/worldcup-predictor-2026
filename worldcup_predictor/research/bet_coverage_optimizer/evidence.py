"""Evidence hashing for coverage recommendations (stable, secret-free)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _canon(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _canon(obj[k]) for k in sorted(obj.keys(), key=lambda x: str(x))}
    if isinstance(obj, (list, tuple)):
        return [_canon(x) for x in obj]
    if isinstance(obj, float):
        return round(obj, 8)
    return obj


def evidence_hash(payload: dict[str, Any]) -> str:
    """Stable SHA-256 over canonical JSON of evidence fields (no secrets)."""
    safe = {k: v for k, v in payload.items() if "key" not in str(k).lower() or k in {"market_key", "evidence_hash"}}
    # Drop any accidental secret-looking fields
    for banned in ("api_key", "authorization", "token", "password", "secret"):
        safe.pop(banned, None)
    raw = json.dumps(_canon(safe), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
