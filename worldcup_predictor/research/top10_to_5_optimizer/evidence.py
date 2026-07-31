"""Evidence hashing — deterministic, auditable."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def evidence_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def immutable_flags() -> dict[str, Any]:
    return {
        "research_only": True,
        "owner_only": True,
        "not_deployed": True,
        "canonical_wde_unchanged": True,
        "canonical_ecse_unchanged": True,
        "exact_v2_not_promoted": True,
        "freezes_unchanged": True,
        "coverage_optimizer_unchanged": True,
        "insurance_optimizer_unchanged": True,
        "portfolio_unchanged": True,
        "similarity_unchanged": True,
        "no_fabricated_odds": True,
        "no_production_writes": True,
    }
