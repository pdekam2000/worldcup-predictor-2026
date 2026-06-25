#!/usr/bin/env python3
"""Build Phase 54H-4 target fixture manifest (recent completed, not imported)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h4_pressure_backfill_batch1"

# Known legacy IDs returning HTTP 200 with zero pressure (54H-3 probes).
LEGACY_ZERO_PRESSURE_IDS = frozenset(
    {
        1058472,
        1058474,
        1058475,
        1058476,
        1058477,
        1059947,
        1059951,
        18151401,
        18151402,
        18151403,
        18151404,
        18151405,
    }
)

LEAGUE_ORDER = (732, 2, 5, 2286)
_FINISHED = {5, 7, 8}
_MIN_FIXTURE_ID_RECENT = 19_000_000


def _discover_recent(league_id: int, *, per_league: int = 40) -> list[dict]:
    from worldcup_predictor.feature_store.pressure_store.sportmonks_pressure_store import SportmonksPressureFeatureStore

    store = SportmonksPressureFeatureStore()
    season = store.resolve_season_id(league_id)
    fixtures = store.discover_fixtures(league_id=league_id, season_id=season, max_pages=8)
    imported = store.repo.imported_pressure_fixture_ids()
    rows: list[dict] = []
    for fx in sorted(fixtures, key=lambda x: str(x.get("starting_at") or ""), reverse=True):
        sm_id = int(fx.get("id") or 0)
        if sm_id <= 0:
            continue
        if sm_id in imported:
            continue
        if sm_id in LEGACY_ZERO_PRESSURE_IDS:
            continue
        if sm_id < _MIN_FIXTURE_ID_RECENT and league_id != 732:
            continue
        state_id = int(fx.get("state_id") or 0)
        if state_id not in _FINISHED:
            continue
        rows.append(
            {
                "fixture_id": sm_id,
                "league_id": league_id,
                "season_id": fx.get("season_id") or season,
                "date": fx.get("starting_at"),
                "state_id": state_id,
                "already_imported": False,
                "reason_selected": f"recent_finished_league_{league_id}",
            }
        )
        if len(rows) >= per_league:
            break
    return rows


def build_manifest(*, target_total: int = 100) -> dict:
    fixtures: list[dict] = []
    for league_id in LEAGUE_ORDER:
        need = max(10, target_total - len(fixtures))
        per = min(40, need)
        fixtures.extend(_discover_recent(league_id, per_league=per))
        if len(fixtures) >= target_total:
            break
    fixtures = fixtures[:target_total]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "54H-4",
        "target_total": target_total,
        "fixture_count": len(fixtures),
        "league_order": list(LEAGUE_ORDER),
        "legacy_excluded_count": len(LEGACY_ZERO_PRESSURE_IDS),
        "fixtures": fixtures,
    }


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(target_total=100)
    path = ARTIFACT_DIR / "target_fixtures.json"
    path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"fixture_count": manifest["fixture_count"], "path": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
