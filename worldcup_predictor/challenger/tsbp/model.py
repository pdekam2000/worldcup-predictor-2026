"""TSBP-1 Challenger model (not GBGM)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.challenger.models.base import ChallengerModel
from worldcup_predictor.challenger.tsbp.constants import (
    BIVARIATE_CORR,
    MAX_GOALS_GRID,
    TSBP_FINAL_DECISION_AUTHORITY,
    TSBP_IS_SHADOW,
    TSBP_MODEL_FAMILY,
    TSBP_MODEL_ID,
    TSBP_MODEL_NAME,
    TSBP_MODEL_VERSION,
    TSBP_PUBLIC_VISIBLE,
    TSBP_STATUS,
)
from worldcup_predictor.challenger.tsbp.outputs import bivariate_goals_to_markets
from worldcup_predictor.challenger.tsbp.strength import fit_strength_from_conn, predict_lambdas


class TSBPChallenger(ChallengerModel):
    def __init__(self, *, model_version: str = TSBP_MODEL_VERSION, corr: float = BIVARIATE_CORR):
        self.model_id = TSBP_MODEL_ID
        self.model_version = model_version
        self.model_name = TSBP_MODEL_NAME
        self.model_family = TSBP_MODEL_FAMILY
        self.corr = corr
        self.strength: dict[str, Any] | None = None
        self.train_meta: dict[str, Any] = {}

    def required_features(self) -> tuple[str, ...]:
        return ("competition_key", "home_team_id", "away_team_id")

    def fit(self, X, y_home, y_away, *, sample_meta: dict[str, Any] | None = None) -> dict[str, Any]:
        """Optional offline fit from row dicts; prefer fit_from_conn for forward."""
        # Accept list of row dicts with competition_key / team ids / goals
        rows = X if isinstance(X, list) else []
        from worldcup_predictor.challenger.phase3b.baselines import fit_team_strength

        # Convert string keys later in predict path; store tuple-keyed interim via baselines then remap
        raw = fit_team_strength(rows)
        attack = {f"{c}:{t}": v for (c, t), v in raw["attack"].items()}
        defence = {f"{c}:{t}": v for (c, t), v in raw["defence"].items()}
        self.strength = {
            "league_means": raw["league_means"],
            "attack": attack,
            "defence": defence,
            "games": {},
            "min_games": raw["min_games"],
            "method": {"source": "offline_rows"},
        }
        self.train_meta = {"n": len(rows), "sample_meta": sample_meta or {}}
        return self.train_meta

    def fit_from_conn(self, conn, competition_keys: list[str], *, before_kickoff: str | None = None) -> dict[str, Any]:
        self.strength = fit_strength_from_conn(conn, competition_keys, before_kickoff=before_kickoff)
        self.train_meta = {
            "n": self.strength.get("n_fixtures"),
            "artifact_hash": self.strength.get("artifact_hash"),
            "before_kickoff": before_kickoff,
            "competitions": competition_keys,
        }
        return self.train_meta

    def predict(self, X) -> dict[str, Any]:
        if self.strength is None:
            raise RuntimeError("tsbp_not_fitted")
        feats = X if isinstance(X, dict) else (X[0] if isinstance(X, list) and X else {})
        comp = str(feats.get("competition_key") or "")
        hid = int(feats.get("home_team_id") or 0)
        aid = int(feats.get("away_team_id") or 0)
        lam = predict_lambdas(self.strength, competition_key=comp, home_team_id=hid, away_team_id=aid)
        out = bivariate_goals_to_markets(
            lam["lam_h"],
            lam["lam_a"],
            corr=self.corr,
            max_goals=MAX_GOALS_GRID,
            strength_meta={
                "home_attack": lam["home_attack"],
                "away_attack": lam["away_attack"],
                "home_defence": lam["home_defence"],
                "away_defence": lam["away_defence"],
                "league_baseline": lam["league_baseline"],
                "home_advantage": lam["home_advantage"],
            },
        )
        out["model_id"] = self.model_id
        out["model_version"] = self.model_version
        out["status"] = TSBP_STATUS
        out["is_shadow"] = TSBP_IS_SHADOW
        out["public_visible"] = TSBP_PUBLIC_VISIBLE
        out["final_decision_authority"] = TSBP_FINAL_DECISION_AUTHORITY
        out["team_history"] = {"home_games": lam["home_games"], "away_games": lam["away_games"]}
        return out

    def serialize_metadata(self) -> dict[str, Any]:
        base = super().serialize_metadata()
        base.update(
            {
                "model_name": self.model_name,
                "model_family": self.model_family,
                "distribution": "BIVARIATE_POISSON",
                "corr": self.corr,
                "status": TSBP_STATUS,
                "train_meta": self.train_meta,
                "strength_method": (self.strength or {}).get("method"),
                "artifact_hash": (self.strength or {}).get("artifact_hash"),
            }
        )
        return base
