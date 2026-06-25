"""Build player-level goalscorer features from player feature store tables."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from sqlalchemy import text

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.postgres.session import postgres_configured, session_scope
from worldcup_predictor.egie.goalscorer_shadow.models import FEATURE_COLUMNS

logger = logging.getLogger(__name__)


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


class GoalscorerFeatureBuilder:
    """Load and enrich player-fixture rows from PostgreSQL feature store."""

    def load_player_fixture_rows(self) -> pd.DataFrame:
        if not postgres_configured():
            raise RuntimeError("PostgreSQL not configured — run Phase 54J import first")
        with session_scope() as session:
            rows = session.execute(
                text(
                    """
                    SELECT
                        ms.sportmonks_fixture_id,
                        ms.fixture_id,
                        ms.player_id,
                        ms.player_name,
                        ms.team_id,
                        ms.position AS match_position,
                        ms.starter,
                        ms.captain,
                        ms.minutes AS match_minutes,
                        ms.goals AS match_goals,
                        ms.assists AS match_assists,
                        ms.shots AS match_shots,
                        ms.shots_on_target AS match_shots_on_target,
                        ms.xg AS match_xg,
                        ms.league_id,
                        ms.season_id,
                        ms.match_date,
                        rf.goals_last_3,
                        rf.goals_last_5,
                        rf.goals_last_10,
                        rf.assists_last_5,
                        rf.minutes_last_5,
                        rf.starts_last_5,
                        rf.shots_last_5,
                        rf.shots_on_target_last_5,
                        rf.xg_last_5,
                        rf.xg_last_10,
                        rf.goals_per_90,
                        rf.xg_per_90,
                        rf.starter_probability,
                        rf.recent_form_score,
                        rf.position,
                        rf.position_group,
                        rf.formation,
                        rf.lineup_available,
                        rf.lineup_quality_score,
                        rf.starting_xi_json,
                        rf.bench_json,
                        rf.goalkeeper_player_id
                    FROM fs_player_match_stats ms
                    INNER JOIN fs_player_rolling_features rf
                        ON ms.sportmonks_fixture_id = rf.sportmonks_fixture_id
                       AND ms.player_id = rf.player_id
                    ORDER BY ms.match_date NULLS LAST, ms.sportmonks_fixture_id, ms.player_id
                    """
                )
            ).mappings().all()
        return pd.DataFrame([dict(r) for r in rows])

    def enrich_features(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        out = df.copy()
        out["starter_probability"] = out["starter_probability"].apply(lambda x: _safe_float(x))
        out["goals_per_90"] = out["goals_per_90"].apply(lambda x: _safe_float(x))
        out["xg_per_90"] = out["xg_per_90"].apply(lambda x: _safe_float(x))
        out["recent_form_score"] = out["recent_form_score"].apply(lambda x: _safe_float(x))
        for col in ("goals_last_3", "goals_last_5", "goals_last_10", "assists_last_5", "minutes_last_5",
                    "starts_last_5", "shots_last_5", "shots_on_target_last_5"):
            out[col] = out[col].fillna(0).astype(int)
        for col in ("xg_last_5", "xg_last_10"):
            out[col] = out[col].apply(lambda x: _safe_float(x) if x is not None else 0.0)

        out["expected_minutes"] = (
            out["starter_probability"] * 90.0 + (1.0 - out["starter_probability"]) * 18.0
        ).round(2)

        pos = out["position_group"].fillna(out["position"]).fillna(out["match_position"])
        out["position"] = pos
        out["lineup_status"] = out.apply(_lineup_status, axis=1)

        team_means = (
            out.groupby(["sportmonks_fixture_id", "team_id"])["goals_per_90"]
            .mean()
            .rename("team_strength_proxy")
        )
        out = out.merge(team_means, on=["sportmonks_fixture_id", "team_id"], how="left")
        out["team_strength_proxy"] = out["team_strength_proxy"].fillna(0.0)

        fixture_teams = out.groupby("sportmonks_fixture_id")["team_id"].apply(lambda s: list(s.unique())).to_dict()
        opp_def: list[float] = []
        for _, row in out.iterrows():
            fid = int(row["sportmonks_fixture_id"])
            tid = row["team_id"]
            teams = fixture_teams.get(fid, [])
            opp_ids = [t for t in teams if t != tid]
            if not opp_ids:
                opp_def.append(0.0)
                continue
            opp_id = opp_ids[0]
            opp_rows = out[(out["sportmonks_fixture_id"] == fid) & (out["team_id"] == opp_id)]
            opp_def.append(float(opp_rows["goals_last_5"].mean()) if len(opp_rows) else 0.0)
        out["opponent_defense_proxy"] = opp_def

        return out

    def apply_eligibility(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return (eligible, unusable) with reason column on unusable."""
        if df.empty:
            return df, df.copy()

        records: list[dict[str, Any]] = []
        unusable: list[dict[str, Any]] = []

        for _, row in df.iterrows():
            reason = _ineligible_reason(row)
            row_dict = row.to_dict()
            if reason:
                row_dict["unusable_reason"] = reason
                unusable.append(row_dict)
            else:
                records.append(row_dict)

        eligible = pd.DataFrame(records) if records else pd.DataFrame(columns=df.columns)
        bad = pd.DataFrame(unusable) if unusable else pd.DataFrame(columns=list(df.columns) + ["unusable_reason"])
        return eligible, bad


def _lineup_status(row: pd.Series) -> str:
    if not bool(row.get("lineup_available")):
        return "unknown"
    if bool(row.get("starter")):
        return "starter"
    xi = row.get("starting_xi_json") or []
    bench = row.get("bench_json") or []
    pid = int(row.get("player_id") or 0)
    if isinstance(xi, list) and pid in [int(x) for x in xi if x is not None]:
        return "starter"
    if isinstance(bench, list) and pid in [int(x) for x in bench if x is not None]:
        return "bench"
    return "squad"


def _ineligible_reason(row: pd.Series) -> str | None:
    status = row.get("lineup_status") or _lineup_status(row)
    if status not in ("starter", "bench"):
        return "not_in_lineup"

    minutes_hist = int(row.get("minutes_last_5") or 0)
    starts_hist = int(row.get("starts_last_5") or 0)
    if minutes_hist <= 0 and starts_hist <= 0:
        return "no_minutes_history"

    pos = str(row.get("position") or row.get("position_group") or "").upper()
    gk_id = row.get("goalkeeper_player_id")
    try:
        pid = int(row.get("player_id") or 0)
        gk_int = int(gk_id) if gk_id is not None and pd.notna(gk_id) else None
    except (TypeError, ValueError):
        pid = 0
        gk_int = None
    is_gk = pos == "GK" or (gk_int is not None and gk_int == pid)
    if is_gk and int(row.get("match_goals") or 0) == 0:
        return "goalkeeper_excluded"

    return None
