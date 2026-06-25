"""STEP 4 — UEFA EGIE provider feature store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.config import PROVIDER_SPORTMONKS
from worldcup_predictor.egie.provider_features.models import ProviderFeatureVector
from worldcup_predictor.egie.storage.repository import EgieRawStoreRepository
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache, uefa_data_root
from worldcup_predictor.egie.uefa_club.feature_extractors import build_provider_vector_fields


class UefaClubFeatureStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.egie_raw = EgieRawStoreRepository(self.settings)
        self._cache_root = uefa_data_root(self.settings) / "egie" / "uefa_club" / "raw"

    def _load_payload(self, sportmonks_fixture_id: int) -> Any:
        cache = self._cache_root / f"{sportmonks_fixture_id}.json"
        legacy = uefa_data_root(self.settings) / "data" / "egie" / "uefa_club" / "raw" / f"{sportmonks_fixture_id}.json"
        for path in (cache, legacy):
            if not path.is_file():
                continue
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
                return blob.get("payload")
            except (json.JSONDecodeError, OSError):
                pass
        for resource in ("fixture_enrichment", "xg", "fixtures"):
            row = self.egie_raw.get_latest_raw(
                provider=PROVIDER_SPORTMONKS,
                resource_type=resource,
                fixture_id=int(sportmonks_fixture_id),
            )
            if row and row.get("payload_json"):
                return row["payload_json"]
        return None

    def build(
        self,
        sportmonks_fixture_id: int,
        *,
        competition_key: str,
        home_team: str = "",
        away_team: str = "",
    ) -> ProviderFeatureVector:
        payload = self._load_payload(int(sportmonks_fixture_id))
        fields = build_provider_vector_fields(payload)
        coverage = fields.pop("coverage", {})
        sources = {k: "sportmonks_uefa_ingest" for k, v in coverage.items() if v}
        return ProviderFeatureVector(
            fixture_id=int(sportmonks_fixture_id),
            competition_key=competition_key,
            home_xg_for=fields.get("home_xg_for"),
            away_xg_for=fields.get("away_xg_for"),
            home_xg_against=fields.get("away_xg"),
            away_xg_against=fields.get("home_xg"),
            pressure_index_home=fields.get("pressure_index_home"),
            pressure_index_away=fields.get("pressure_index_away"),
            odds_implied_home=fields.get("odds_implied_home"),
            odds_implied_draw=fields.get("odds_implied_draw"),
            odds_implied_away=fields.get("odds_implied_away"),
            odds_movement_home=fields.get("odds_movement"),
            lineup_strength_home=fields.get("lineup_strength_home"),
            lineup_strength_away=fields.get("lineup_strength_away"),
            coverage=coverage,
            sources=sources,
        )

    def audit_utilization(self, fixture_ids: list[int], *, competition_key: str) -> dict[str, Any]:
        counts = {k: 0 for k in ("xg", "pressure", "odds", "predictions", "lineups", "events", "statistics")}
        n = len(fixture_ids)
        for fid in fixture_ids:
            vec = self.build(fid, competition_key=competition_key)
            for k in counts:
                if (vec.coverage or {}).get(k):
                    counts[k] += 1
        return {
            "fixtures": n,
            "coverage_count": counts,
            "coverage_pct": {k: round(100 * v / n, 2) if n else 0 for k, v in counts.items()},
        }
