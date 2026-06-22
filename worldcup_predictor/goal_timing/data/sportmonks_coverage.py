"""Sportmonks coverage probe — no mass import (Phase 51C)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository


def probe_sportmonks_goal_timing_coverage(
    *,
    settings: Settings | None = None,
    sample_fixture_ids: list[int] | None = None,
) -> dict[str, Any]:
    """
    Read-only coverage check for Sportmonks xG / advanced stats.
    Does not import or call Sportmonks unless explicitly configured and probed per fixture.
    """
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    configured = bool(settings.sportmonks_configured)
    xg_snapshots = 0
    if sample_fixture_ids:
        for fid in sample_fixture_ids[:20]:
            if repo.has_xg_snapshot(int(fid)):
                xg_snapshots += 1

    return {
        "sportmonks_configured": configured,
        "mass_import_enabled": False,
        "xg_snapshots_in_sample": xg_snapshots,
        "sample_size": len(sample_fixture_ids or []),
        "note": (
            "Sportmonks goal-timing enrichment is probe-only in Phase 51C. "
            "Enable targeted fetch in a later phase after coverage is confirmed."
        ),
    }
