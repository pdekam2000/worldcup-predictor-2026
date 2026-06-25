"""Historical goalscorer dataset builder — targets + exports."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.goalscorer_shadow.feature_builder import GoalscorerFeatureBuilder
from worldcup_predictor.egie.goalscorer_shadow.models import GoalscorerDatasetSummary

logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path("artifacts/phase54k_goalscorer_shadow")

_CACHE_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_pressure/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first_goal_map_from_cache(fixture_ids: set[int]) -> dict[int, int | None]:
    """fixture_id -> first goal scorer player_id (cache-first)."""
    out: dict[int, int | None] = {}
    seen_paths: set[Path] = set()
    remaining = set(fixture_ids)

    for root in _CACHE_ROOTS:
        if not root.is_dir() or not remaining:
            continue
        for path in root.glob("*.json"):
            if path in seen_paths:
                continue
            seen_paths.add(path)
            try:
                sm_id = int(path.stem)
            except ValueError:
                continue
            if sm_id not in remaining:
                continue
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            data = (blob.get("payload") or {}).get("data")
            if not isinstance(data, dict):
                continue
            fid = int(data.get("id") or sm_id)
            out[fid] = _first_goal_player_id(data)
            remaining.discard(fid)

    for fid in remaining:
        out.setdefault(fid, None)
    return out


def _first_goal_player_id(data: dict[str, Any]) -> int | None:
    goals: list[tuple[int, int, int]] = []
    for ev in data.get("events") or []:
        if not isinstance(ev, dict):
            continue
        t = ev.get("type") or {}
        dev = str(t.get("developer_name") or t.get("name") or "").upper()
        if "GOAL" not in dev or "OWN" in dev:
            continue
        try:
            minute = int(ev.get("minute") if ev.get("minute") is not None else 999)
            sort_order = int(ev.get("sort_order") or 0)
            pid = int(ev.get("player_id") or 0)
        except (TypeError, ValueError):
            continue
        if pid > 0:
            goals.append((minute, sort_order, pid))
    if not goals:
        return None
    goals.sort(key=lambda x: (x[0], x[1]))
    return goals[0][2]


def _most_likely_scorer_id(fixture_df: pd.DataFrame) -> int | None:
    scorers = fixture_df[fixture_df["match_goals"].fillna(0).astype(int) > 0]
    if scorers.empty:
        return None
    max_goals = scorers["match_goals"].max()
    top = scorers[scorers["match_goals"] == max_goals]
    if len(top) == 1:
        return int(top.iloc[0]["player_id"])
    return int(top.sort_values("match_minutes").iloc[0]["player_id"])


def temporal_split(df: pd.DataFrame, train_frac: float = 0.7, val_frac: float = 0.15) -> pd.DataFrame:
    out = df.copy()
    if "match_date" in out.columns:
        out = out.sort_values("match_date").reset_index(drop=True)
    n = len(out)
    if n == 0:
        out["split"] = []
        return out
    train_end = max(1, int(n * train_frac))
    val_end = max(train_end + 1, int(n * (train_frac + val_frac)))
    splits = ["train"] * train_end + ["val"] * (val_end - train_end) + ["test"] * (n - val_end)
    out["split"] = splits[:n]
    return out


class GoalscorerDatasetBuilder:
    def __init__(self, artifact_dir: Path | str | None = None) -> None:
        self.artifact_dir = Path(artifact_dir or ARTIFACT_DIR)
        self.feature_builder = GoalscorerFeatureBuilder()

    def build(self) -> tuple[pd.DataFrame, pd.DataFrame, GoalscorerDatasetSummary]:
        raw = self.feature_builder.load_player_fixture_rows()
        enriched = self.feature_builder.enrich_features(raw)
        eligible, unusable = self.feature_builder.apply_eligibility(enriched)

        fixture_ids = set(int(x) for x in eligible["sportmonks_fixture_id"].unique()) if not eligible.empty else set()
        first_goal_map = _first_goal_map_from_cache(fixture_ids)

        if not eligible.empty:
            eligible = eligible.copy()
            eligible["target_anytime"] = (eligible["match_goals"].fillna(0).astype(int) >= 1).astype(int)
            eligible["first_goal_player_id"] = eligible["sportmonks_fixture_id"].map(
                lambda fid: first_goal_map.get(int(fid))
            )
            eligible["target_first_goal"] = (
                eligible["player_id"].astype(int) == eligible["first_goal_player_id"].fillna(-1).astype(int)
            ).astype(int)

            def _ml_for_group(grp: pd.DataFrame) -> pd.Series:
                ml = _most_likely_scorer_id(grp)
                return (grp["player_id"].astype(int) == (ml or -1)).astype(int)

            eligible["target_most_likely"] = (
                eligible.groupby("sportmonks_fixture_id", group_keys=False).apply(_ml_for_group)
            )
            eligible = temporal_split(eligible)
        else:
            eligible = pd.DataFrame()

        summary = GoalscorerDatasetSummary(
            total_rows=len(enriched),
            eligible_rows=len(eligible),
            unusable_rows=len(unusable),
            fixtures=int(eligible["sportmonks_fixture_id"].nunique()) if not eligible.empty else 0,
            anytime_positive=int(eligible["target_anytime"].sum()) if not eligible.empty else 0,
            first_goal_positive=int(eligible["target_first_goal"].sum()) if not eligible.empty else 0,
            train_rows=int((eligible["split"] == "train").sum()) if not eligible.empty else 0,
            val_rows=int((eligible["split"] == "val").sum()) if not eligible.empty else 0,
            test_rows=int((eligible["split"] == "test").sum()) if not eligible.empty else 0,
            date_min=str(eligible["match_date"].min()) if not eligible.empty and eligible["match_date"].notna().any() else None,
            date_max=str(eligible["match_date"].max()) if not eligible.empty and eligible["match_date"].notna().any() else None,
        )
        return eligible, unusable, summary

    def export(
        self,
        eligible: pd.DataFrame,
        unusable: pd.DataFrame,
        summary: GoalscorerDatasetSummary,
    ) -> dict[str, str]:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        paths: dict[str, str] = {}

        parquet_path = self.artifact_dir / "goalscorer_dataset.parquet"
        csv_path = self.artifact_dir / "goalscorer_dataset.csv"
        eligible.to_parquet(parquet_path, index=False)
        eligible.to_csv(csv_path, index=False)
        paths["parquet"] = str(parquet_path)
        paths["csv"] = str(csv_path)

        summary_path = self.artifact_dir / "goalscorer_dataset_summary.json"
        payload = summary.to_dict()
        payload["generated_at"] = _utc_now()
        summary_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        paths["summary"] = str(summary_path)

        unusable_path = self.artifact_dir / "unusable_goalscorer_rows.csv"
        unusable.to_csv(unusable_path, index=False)
        paths["unusable"] = str(unusable_path)

        return paths
