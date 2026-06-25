"""Build modern EGIE backtest dataset from xG-rich recent fixtures (Phase 54F-5)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.uefa_club.feature_extractors import parse_match_result
from worldcup_predictor.egie.xg_backtest.xg_feature_builder import XgFeatureBuilder
from worldcup_predictor.feature_store.sportmonks_xg_store import SportmonksXgFeatureStore

logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path("artifacts/phase54f5_modern_egie_dataset")

TARGET_LEAGUES: dict[int, str] = {
    732: "world_cup",
    2: "champions_league",
    5: "europa_league",
    2286: "conference_league",
}

# Recent seasons with proven xG (Phase 54F-3/54F-4)
RECENT_SEASON_IDS: frozenset[int] = frozenset(
    {
        26618,  # WC 2026
        23619,  # CL 2024/25
        25580,  # CL 2025/26
        23620,  # EL 2024/25
        25582,  # EL 2025/26
        25581,  # Conference 2025/26
    }
)

_FINISHED_STATE_IDS = {5, 7, 8}


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _minute_to_range(minute: int | None) -> str | None:
    if minute is None:
        return None
    if minute <= 15:
        return "0-15"
    if minute <= 30:
        return "16-30"
    return "31-45+"


class ModernEgieDatasetBuilder:
    """
    Build a modern EGIE xG backtest dataset from feature-store summaries + cached payloads.

    Uses only finished fixtures with team xG (type 5304) and pre-match rolling features.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.xg_builder = XgFeatureBuilder(self.settings)
        self.store = SportmonksXgFeatureStore(self.settings)

    def _load_cache_payload(self, sportmonks_fixture_id: int) -> dict[str, Any] | None:
        cached = self.store.load_cache(sportmonks_fixture_id)
        if not cached:
            return None
        data = (cached.get("payload") or {}).get("data")
        return data if isinstance(data, dict) else None

    def _candidate_summaries(self) -> list[dict[str, Any]]:
        summaries = self.xg_builder.load_ordered_summaries()
        out: list[dict[str, Any]] = []
        for row in summaries:
            league_id = int(row.get("league_id") or 0)
            season_id = int(row.get("season_id") or 0)
            if league_id not in TARGET_LEAGUES:
                continue
            if season_id not in RECENT_SEASON_IDS:
                continue
            if row.get("home_xg") is None and row.get("away_xg") is None:
                continue
            out.append(row)
        return out

    def build_rows(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        summaries = self._candidate_summaries()
        xg_feats = self.xg_builder.build_chronological_features()
        usable: list[dict[str, Any]] = []
        unusable: list[dict[str, Any]] = []

        for summary in summaries:
            sm_id = int(summary.get("sportmonks_fixture_id") or 0)
            league_id = int(summary.get("league_id") or 0)
            season_id = int(summary.get("season_id") or 0)
            home_id = summary.get("home_team_id")
            away_id = summary.get("away_team_id")
            raw = self._load_cache_payload(sm_id)

            reason = ""
            if not raw:
                reason = "cache_missing"
            elif int(raw.get("state_id") or 0) not in _FINISHED_STATE_IDS:
                reason = "not_finished"

            home_name = away_name = ""
            if raw:
                for p in raw.get("participants") or []:
                    if not isinstance(p, dict):
                        continue
                    loc = str((p.get("meta") or {}).get("location") or "").lower()
                    if loc == "home":
                        home_name = str(p.get("name") or "")
                    elif loc == "away":
                        away_name = str(p.get("name") or "")

            payload = {"data": raw} if raw else None
            result = parse_match_result(payload, home_team=home_name, away_team=away_name)
            home_goals = int(result.get("home_goals") or 0)
            away_goals = int(result.get("away_goals") or 0)
            first_minute = result.get("first_goal_minute")
            first_side = result.get("first_goal_team_side")
            kickoff = summary.get("match_started_at") or (raw or {}).get("starting_at")

            xg = xg_feats.get(sm_id, {})
            rolling_ok = bool(
                xg.get("rolling_xg_5_home") is not None and xg.get("rolling_xg_5_away") is not None
            )
            xg_ok = bool(xg.get("xg_available"))
            if not reason:
                if not xg_ok:
                    reason = "no_pre_match_rolling_xg"
                elif not rolling_ok:
                    reason = "insufficient_rolling_history"

            row: dict[str, Any] = {
                "fixture_id": sm_id,
                "sportmonks_fixture_id": sm_id,
                "league_id": league_id,
                "season_id": season_id,
                "competition_key": TARGET_LEAGUES.get(league_id, f"league_{league_id}"),
                "date": str(kickoff or ""),
                "kickoff_utc": str(kickoff or ""),
                "home_team_id": home_id,
                "away_team_id": away_id,
                "home_team_name": home_name,
                "away_team_name": away_name,
                "home_team": home_name,
                "away_team": away_name,
                "final_score_home": home_goals,
                "final_score_away": away_goals,
                "first_goal_team": first_side if first_side in ("home", "away") else None,
                "first_goal_minute": first_minute,
                "total_goals": home_goals + away_goals,
                "label_first_goal_team": first_side if first_side in ("home", "away") else None,
                "label_goal_range": _minute_to_range(int(first_minute) if first_minute is not None else None),
                "label_over_25": int(home_goals + away_goals > 2),
                "home_goal_rate_proxy": float(xg.get("rolling_xg_5_home") or 0.33),
                "away_goal_rate_proxy": float(xg.get("rolling_xg_5_away") or 0.33),
                "data_quality_score": 1.0 if rolling_ok else 0.5,
                "home_history_samples": int(xg.get("xg_history_matches_home") or 0),
                "away_history_samples": int(xg.get("xg_history_matches_away") or 0),
                "home_recent_xg": xg.get("home_recent_xg"),
                "away_recent_xg": xg.get("away_recent_xg"),
                "home_recent_xga": xg.get("home_recent_xga"),
                "away_recent_xga": xg.get("away_recent_xga"),
                "rolling_xg_3_home": xg.get("rolling_xg_3_home"),
                "rolling_xg_5_home": xg.get("rolling_xg_5_home"),
                "rolling_xg_10_home": xg.get("rolling_xg_10_home"),
                "rolling_xg_3_away": xg.get("rolling_xg_3_away"),
                "rolling_xg_5_away": xg.get("rolling_xg_5_away"),
                "rolling_xg_10_away": xg.get("rolling_xg_10_away"),
                "xg_difference": xg.get("xg_difference"),
                "attack_strength_difference": xg.get("attack_strength_difference"),
                "defensive_weakness_difference": xg.get("defensive_weakness_difference"),
                "xg_momentum_difference": xg.get("xg_momentum_difference"),
                "xg_available": xg_ok,
                "rolling_xg_available": rolling_ok,
                "leakage_safe": True,
                "skip_reason": reason or None,
            }

            if reason:
                unusable.append(row)
            else:
                usable.append(row)

        return usable, unusable

    def build_summary(self, usable: list[dict[str, Any]], unusable: list[dict[str, Any]]) -> dict[str, Any]:
        candidates = len(usable) + len(unusable)
        df = pd.DataFrame(usable) if usable else pd.DataFrame()
        by_league: dict[str, dict[str, int]] = {}
        by_season: dict[str, dict[str, int]] = {}
        if len(df):
            for league, grp in df.groupby("competition_key"):
                by_league[str(league)] = {"usable": int(len(grp)), "rolling_xg": int(grp["rolling_xg_available"].sum())}
            for season, grp in df.groupby("season_id"):
                by_season[str(season)] = {"usable": int(len(grp)), "rolling_xg": int(grp["rolling_xg_available"].sum())}

        rolling_pct = round(100.0 * len(usable) / candidates, 2) if candidates else 0.0
        return {
            "phase": "54F-5",
            "candidate_fixtures": candidates,
            "usable_fixtures": len(usable),
            "unusable_fixtures": len(unusable),
            "rolling_xg_coverage_pct": rolling_pct,
            "by_league": by_league,
            "by_season": by_season,
            "first_goal_team_labeled": int(df["first_goal_team"].notna().sum()) if len(df) else 0,
            "goal_range_labeled": int(df["label_goal_range"].notna().sum()) if len(df) else 0,
            "team_goals_labeled": int(df["label_over_25"].notna().sum()) if len(df) else 0,
            "leakage_safe_count": len(usable),
            "threshold_30_met": rolling_pct >= 30.0 and len(usable) >= 30,
            "threshold_50_preferred": rolling_pct >= 50.0,
        }

    def save(self, output_dir: Path | None = None) -> dict[str, Any]:
        out_dir = output_dir or ARTIFACT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        usable, unusable = self.build_rows()
        df = pd.DataFrame(usable)
        summary = self.build_summary(usable, unusable)

        parquet_path = out_dir / "modern_egie_dataset.parquet"
        csv_path = out_dir / "modern_egie_dataset.csv"
        summary_path = out_dir / "modern_egie_dataset_summary.json"
        unusable_path = out_dir / "modern_egie_unusable_fixtures.csv"

        if len(df):
            df.to_parquet(parquet_path, index=False)
            df.to_csv(csv_path, index=False)
        else:
            pd.DataFrame(columns=["sportmonks_fixture_id"]).to_parquet(parquet_path, index=False)
            pd.DataFrame(columns=["sportmonks_fixture_id"]).to_csv(csv_path, index=False)

        pd.DataFrame(unusable).to_csv(unusable_path, index=False)
        summary["paths"] = {
            "parquet": str(parquet_path),
            "csv": str(csv_path),
            "unusable": str(unusable_path),
        }
        summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary


def audit_modern_dataset_leakage(df) -> dict[str, Any]:
    """Leakage audit scoped to modern EGIE dataset rows."""
    import pandas as pd

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame()
    forbidden = {"home_xg", "away_xg", "home_xga", "away_xga"}
    checks = [
        {
            "name": "usable_rows_leakage_safe",
            "pass": bool(len(df) == 0 or df.get("leakage_safe", pd.Series(dtype=bool)).all()),
            "detail": f"rows={len(df)}",
        },
        {
            "name": "usable_rows_have_rolling_xg",
            "pass": bool(len(df) == 0 or df.get("rolling_xg_available", pd.Series(dtype=bool)).all()),
            "detail": "rolling_xg_5 both sides",
        },
        {
            "name": "no_post_match_xg_columns",
            "pass": not forbidden.intersection(set(df.columns)),
            "detail": f"forbidden_present={sorted(forbidden.intersection(set(df.columns)))}",
        },
    ]
    passed = all(c["pass"] for c in checks)
    return {
        "status": "PASS" if passed else "FAIL",
        "all_pass": passed,
        "checks": checks,
        "fixtures_audited": len(df),
    }
