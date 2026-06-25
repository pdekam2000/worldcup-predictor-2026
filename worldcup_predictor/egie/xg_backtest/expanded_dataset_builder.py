"""Build expanded modern EGIE xG backtest dataset (Phase 54F-6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.xg_backtest.expansion_config import PRIORITY_LEAGUES, eligible_seasons
from worldcup_predictor.egie.xg_backtest.modern_dataset_builder import (
    ModernEgieDatasetBuilder,
    audit_modern_dataset_leakage,
    _minute_to_range,
    _FINISHED_STATE_IDS,
)
from worldcup_predictor.egie.uefa_club.feature_extractors import parse_match_result

ARTIFACT_DIR = Path("artifacts/phase54f6_expanded_dataset")


class ExpandedEgieDatasetBuilder(ModernEgieDatasetBuilder):
    """Expanded dataset — all eligible recent seasons from DB, not hardcoded season IDs."""

    def _eligible_season_ids(self) -> frozenset[int]:
        ids: set[int] = set()
        for row in eligible_seasons(min_coverage_pct=30.0):
            if row.get("included"):
                ids.add(int(row["season_id"]))
        # Always include seasons already in feature store for priority leagues (2024+)
        for row in self.xg_builder.load_ordered_summaries():
            lid = int(row.get("league_id") or 0)
            sid = int(row.get("season_id") or 0)
            if lid in PRIORITY_LEAGUES and sid > 0:
                ids.add(sid)
        return frozenset(ids)

    def _candidate_summaries(self) -> list[dict[str, Any]]:
        season_ids = self._eligible_season_ids()
        summaries = self.xg_builder.load_ordered_summaries()
        out: list[dict[str, Any]] = []
        for row in summaries:
            league_id = int(row.get("league_id") or 0)
            season_id = int(row.get("season_id") or 0)
            if league_id not in PRIORITY_LEAGUES:
                continue
            if season_id not in season_ids:
                continue
            if row.get("home_xg") is None and row.get("away_xg") is None:
                continue
            out.append(row)
        return out

    def build_summary(self, usable: list[dict[str, Any]], unusable: list[dict[str, Any]]) -> dict[str, Any]:
        summary = super().build_summary(usable, unusable)
        summary["phase"] = "54F-6"
        df = pd.DataFrame(usable) if usable else pd.DataFrame()
        candidates = len(usable) + len(unusable)

        rolling_3 = rolling_5 = rolling_10 = 0
        if len(df):
            rolling_3 = int((df["rolling_xg_3_home"].notna() & df["rolling_xg_3_away"].notna()).sum())
            rolling_5 = int((df["rolling_xg_5_home"].notna() & df["rolling_xg_5_away"].notna()).sum())
            rolling_10 = int((df["rolling_xg_10_home"].notna() & df["rolling_xg_10_away"].notna()).sum())

        summary.update(
            {
                "fixtures_scanned": candidates,
                "rolling_xg_3_coverage": rolling_3,
                "rolling_xg_5_coverage": rolling_5,
                "rolling_xg_10_coverage": rolling_10,
                "rolling_xg_3_pct": round(100.0 * rolling_3 / candidates, 2) if candidates else 0.0,
                "rolling_xg_5_pct": round(100.0 * rolling_5 / candidates, 2) if candidates else 0.0,
                "rolling_xg_10_pct": round(100.0 * rolling_10 / candidates, 2) if candidates else 0.0,
                "threshold_300_met": len(usable) >= 300,
                "threshold_500_preferred": len(usable) >= 500,
                "eligible_seasons": sorted(self._eligible_season_ids()),
            }
        )
        return summary

    def save(self, output_dir: Path | None = None) -> dict[str, Any]:
        out_dir = output_dir or ARTIFACT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        usable, unusable = self.build_rows()
        df = pd.DataFrame(usable)
        summary = self.build_summary(usable, unusable)

        paths = {
            "parquet": out_dir / "expanded_egie_dataset.parquet",
            "csv": out_dir / "expanded_egie_dataset.csv",
            "summary": out_dir / "expanded_egie_dataset_summary.json",
            "unusable": out_dir / "expanded_egie_unusable_fixtures.csv",
        }
        if len(df):
            df.to_parquet(paths["parquet"], index=False)
            df.to_csv(paths["csv"], index=False)
        else:
            pd.DataFrame(columns=["sportmonks_fixture_id"]).to_parquet(paths["parquet"], index=False)
            pd.DataFrame(columns=["sportmonks_fixture_id"]).to_csv(paths["csv"], index=False)
        pd.DataFrame(unusable).to_csv(paths["unusable"], index=False)
        summary["paths"] = {k: str(v) for k, v in paths.items()}
        paths["summary"].write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        leakage = audit_modern_dataset_leakage(df)
        (out_dir / "leakage_audit.json").write_text(json.dumps(leakage, indent=2), encoding="utf-8")
        summary["leakage_audit"] = leakage.get("status")
        return summary
