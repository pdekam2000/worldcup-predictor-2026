"""Versioned TSBP domain allowlist."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.challenger.tsbp.constants import (
    DEFAULT_FORWARD_ENABLED,
    DEFAULT_RESEARCH_ONLY,
    DOMAIN_DATA_BLOCKED,
    DOMAIN_FORWARD_ENABLED,
    DOMAIN_POLICY_VERSION,
    DOMAIN_RESEARCH_ONLY,
    DOMAIN_UNSUPPORTED,
    MIN_LEAGUE_HISTORY,
    MIN_TEAM_GAMES,
)

ROOT = Path(__file__).resolve().parents[3]
POLICY_ARTIFACT = ROOT / "artifacts" / "challenger_program" / "phase4b" / "tsbp_domain_policy.json"


def default_domain_policy() -> dict[str, Any]:
    classifications: dict[str, str] = {}
    for c in DEFAULT_FORWARD_ENABLED:
        classifications[c] = DOMAIN_FORWARD_ENABLED
    for c in DEFAULT_RESEARCH_ONLY:
        classifications[c] = DOMAIN_RESEARCH_ONLY
    return {
        "policy_version": DOMAIN_POLICY_VERSION,
        "source": "phase3b_domain_breakdown",
        "min_league_history": MIN_LEAGUE_HISTORY,
        "min_team_games": MIN_TEAM_GAMES,
        "classifications": classifications,
        "notes": [
            "Only premier_league and bundesliga had sufficient Phase 3B coverage with team-strength beating league baseline.",
            "champions_league / world_cup_2026 remain RESEARCH_ONLY (insufficient Challenger snapshot rows).",
            "Other Tier B leagues are UNSUPPORTED until Phase 3B-style evidence exists.",
            "Do not auto-enable every Tier B competition.",
        ],
    }


def load_domain_policy() -> dict[str, Any]:
    if POLICY_ARTIFACT.exists():
        return json.loads(POLICY_ARTIFACT.read_text(encoding="utf-8"))
    return default_domain_policy()


def save_domain_policy(policy: dict[str, Any] | None = None) -> Path:
    POLICY_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    pol = policy or default_domain_policy()
    POLICY_ARTIFACT.write_text(json.dumps(pol, indent=2), encoding="utf-8")
    return POLICY_ARTIFACT


def classify_competition(competition_key: str | None, policy: dict[str, Any] | None = None) -> str:
    pol = policy or load_domain_policy()
    if not competition_key:
        return DOMAIN_UNSUPPORTED
    return str(pol.get("classifications", {}).get(competition_key) or DOMAIN_UNSUPPORTED)


def is_forward_enabled(competition_key: str | None, policy: dict[str, Any] | None = None) -> bool:
    return classify_competition(competition_key, policy) == DOMAIN_FORWARD_ENABLED
