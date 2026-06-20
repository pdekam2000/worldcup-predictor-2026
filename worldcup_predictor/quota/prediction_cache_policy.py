"""Prediction result cache validation — Phase 27 schema versioning."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator

# Bump when specialist orchestrator output shape changes (agent add/remove/rename).
PREDICTION_CACHE_SCHEMA_VERSION = "27-v1"

# MasterAnalysisAgent is excluded from report.signals.
EXPECTED_SPECIALIST_AGENT_COUNT = len(SpecialistOrchestrator.AGENT_CLASSES) - 1

PHASE_22_REQUIRED_AGENT_KEYS: tuple[str, ...] = (
    "expected_lineup_agent",
    "tournament_context_agent",
    "xg_intelligence_agent",
    "sportmonks_prediction_agent",
)


def specialist_agent_count(payload: dict[str, Any]) -> int:
    agents = (payload.get("specialist_summary") or {}).get("agents") or {}
    return len(agents) if isinstance(agents, dict) else 0


def is_prediction_cache_valid(payload: dict[str, Any]) -> tuple[bool, str]:
    """
    Return (valid, reason).

    Invalid entries are treated as cache misses so the pipeline re-runs safely.
    """
    if not isinstance(payload, dict):
        return False, "invalid_payload"

    if payload.get("status") != "ok":
        return False, "non_ok_status"

    version = payload.get("cache_schema_version")
    if version != PREDICTION_CACHE_SCHEMA_VERSION:
        return False, f"schema_version_mismatch:{version or 'missing'}"

    count = specialist_agent_count(payload)
    if count < EXPECTED_SPECIALIST_AGENT_COUNT:
        return False, f"agent_count_{count}_lt_{EXPECTED_SPECIALIST_AGENT_COUNT}"

    agents = (payload.get("specialist_summary") or {}).get("agents") or {}
    if not isinstance(agents, dict):
        return False, "agents_not_dict"

    for key in PHASE_22_REQUIRED_AGENT_KEYS:
        if key not in agents:
            return False, f"missing_{key}"

    return True, "ok"


def stamp_prediction_cache(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach schema metadata before persisting a prediction payload."""
    out = dict(payload)
    out["cache_schema_version"] = PREDICTION_CACHE_SCHEMA_VERSION
    out["specialist_agent_count"] = specialist_agent_count(out)
    return out
