#!/usr/bin/env python3
"""Discover UEFA prior-season finished fixture targets (plan-only, no ingest)."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h5_pressure_expansion"
_UEFA_LEAGUES = (2, 5, 2286)
_FINISHED = {5, 7, 8}
_MIN_FIXTURE_ID = 19_000_000
_SEASON_LABELS = (
    re.compile(r"2025\s*/\s*2026", re.I),
    re.compile(r"2024\s*/\s*2025", re.I),
    re.compile(r"2023\s*/\s*2024", re.I),
)


def _season_label(season: dict) -> str:
    for key in ("name", "year", "starting_at", "ending_at"):
        val = season.get(key)
        if val:
            return str(val)
    return str(season.get("id") or "unknown")


def _label_matches(label: str) -> bool:
    return any(p.search(label) for p in _SEASON_LABELS)


def _recommendation(candidate: int, finished: int) -> str:
    if candidate >= 30:
        return "ready_for_prior_season_backfill"
    if finished > 0 and candidate == 0:
        return "legacy_ids_or_no_pressure_expected"
    if finished == 0:
        return "no_finished_fixtures_in_sample"
    return "low_yield_probe_more_pages"


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository
    from worldcup_predictor.feature_store.pressure_store.sportmonks_pressure_store import SportmonksPressureFeatureStore
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

    settings = get_settings()
    store = SportmonksPressureFeatureStore(settings)
    repo = SportmonksPressureRepository(settings)
    provider = SportmonksProvider(settings)
    imported = repo.imported_pressure_fixture_ids()

    targets: list[dict] = []
    for league_id in _UEFA_LEAGUES:
        _, payload, err = provider.safe_get(
            f"/leagues/{league_id}",
            params={"include": "seasons;currentSeason"},
        )
        if err or not isinstance(payload, dict):
            targets.append(
                {
                    "league_id": league_id,
                    "error": str(err)[:120] if err else "no_payload",
                    "recommendation": "api_error_retry",
                }
            )
            continue

        data = payload.get("data") or {}
        seasons = data.get("seasons") or []
        if not isinstance(seasons, list):
            seasons = []

        for season in seasons:
            if not isinstance(season, dict):
                continue
            label = _season_label(season)
            if not _label_matches(label):
                continue
            season_id = int(season.get("id") or 0)
            if season_id <= 0:
                continue

            fixtures = store.discover_fixtures(league_id=league_id, season_id=season_id, max_pages=8)
            finished = [f for f in fixtures if int(f.get("state_id") or 0) in _FINISHED]
            already = sum(1 for f in finished if int(f.get("id") or 0) in imported)
            candidates = [
                f
                for f in finished
                if int(f.get("id") or 0) not in imported and int(f.get("id") or 0) >= _MIN_FIXTURE_ID
            ]
            targets.append(
                {
                    "league_id": league_id,
                    "season_id": season_id,
                    "season_label": label,
                    "fixtures_sampled": len(fixtures),
                    "finished_fixture_count": len(finished),
                    "already_imported_count": already,
                    "candidate_count": len(candidates),
                    "recommendation": _recommendation(len(candidates), len(finished)),
                }
            )

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "54H-5",
        "mode": "plan_only",
        "leagues": list(_UEFA_LEAGUES),
        "targets": targets,
    }
    (ARTIFACT_DIR / "uefa_prior_season_targets.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({"target_rows": len(targets), "path": str(ARTIFACT_DIR / "uefa_prior_season_targets.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
