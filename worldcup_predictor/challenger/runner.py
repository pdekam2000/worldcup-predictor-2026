"""Challenger runner — shadow predictions beside canonical (never authoritative)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.challenger.comparison import build_prematch_comparison
from worldcup_predictor.challenger.constants import (
    CHALLENGER_FINAL_DECISION_AUTHORITY,
    CHALLENGER_PUBLIC_VISIBLE,
    STATUS_DATA_BLOCKED,
    STATUS_OK,
    STATUS_POST_KICKOFF,
)
from worldcup_predictor.challenger.diagnostics import timed
from worldcup_predictor.challenger.prediction_store import save_comparison, save_freeze, save_prediction
from worldcup_predictor.challenger.schemas import build_challenger_prediction_envelope, utc_now
from worldcup_predictor.challenger.snapshot_reader import build_prematch_feature_snapshot


def run_challenger_for_fixture(
    conn,
    *,
    fixture_id: int,
    model,
    prediction_scope: str = "owner_shadow",
    validation_tier: str | None = None,
    include_market: bool = False,
    canonical_summary: dict[str, Any] | None = None,
    linked_canonical_freeze_id: str | None = None,
) -> dict[str, Any]:
    """
    Canonical processing must remain unaffected by this function's failures.
    Caller should wrap in try/except.
    """
    assert CHALLENGER_PUBLIC_VISIBLE is False
    assert CHALLENGER_FINAL_DECISION_AUTHORITY is False

    with timed("challenger_predict") as diag:
        snap = build_prematch_feature_snapshot(conn, fixture_id, include_market=include_market)
        if snap.get("status") == STATUS_POST_KICKOFF:
            env = build_challenger_prediction_envelope(
                fixture_id=fixture_id,
                model_id=model.model_id,
                model_version=model.model_version,
                outputs={},
                feature_snapshot_id=None,
                feature_snapshot_hash=None,
                prediction_time=utc_now(),
                kickoff=None,
                home_team=None,
                away_team=None,
                competition=None,
                prediction_scope=prediction_scope,
                validation_tier=validation_tier,
                confidence=None,
                data_quality="BLOCKED",
                missing_features=[],
                warnings=["post_kickoff"],
                status=STATUS_POST_KICKOFF,
            )
            return {"prediction": env, "freeze": None, "comparison": None, "diagnostics": diag}

        if snap.get("status") != "OK":
            env = build_challenger_prediction_envelope(
                fixture_id=fixture_id,
                model_id=model.model_id,
                model_version=model.model_version,
                outputs={},
                feature_snapshot_id=snap.get("feature_snapshot_id"),
                feature_snapshot_hash=snap.get("feature_snapshot_hash"),
                prediction_time=snap.get("prediction_time") or utc_now(),
                kickoff=snap.get("kickoff_utc"),
                home_team=snap.get("home_team"),
                away_team=snap.get("away_team"),
                competition=snap.get("competition_key"),
                prediction_scope=prediction_scope,
                validation_tier=validation_tier,
                confidence=None,
                data_quality="CARDS_OR_FEATURES_BLOCKED",
                missing_features=list(snap.get("missing_required") or []),
                warnings=[str(snap.get("reason"))],
                status=STATUS_DATA_BLOCKED,
            )
            save_prediction(conn, env)
            return {"prediction": env, "freeze": None, "comparison": None, "diagnostics": diag}

        outputs = model.predict(snap["features"])
        conf = 55.0
        if outputs.get("hda"):
            conf = round(50 + 40 * max(outputs["hda"].values()), 1)
        env = build_challenger_prediction_envelope(
            fixture_id=fixture_id,
            model_id=model.model_id,
            model_version=model.model_version,
            outputs=outputs,
            feature_snapshot_id=snap.get("feature_snapshot_id"),
            feature_snapshot_hash=snap.get("feature_snapshot_hash"),
            prediction_time=snap.get("prediction_time") or utc_now(),
            kickoff=snap.get("kickoff_utc"),
            home_team=snap.get("home_team"),
            away_team=snap.get("away_team"),
            competition=snap.get("competition_key"),
            prediction_scope=prediction_scope,
            validation_tier=validation_tier,
            confidence=conf,
            data_quality="OK",
            missing_features=[],
            warnings=[],
            status=STATUS_OK,
        )
        save_prediction(conn, env)
        fr = save_freeze(conn, env, linked_canonical_freeze_id=linked_canonical_freeze_id)
        env["freeze_hash"] = fr.get("freeze_hash")
        comparison = None
        if canonical_summary:
            comparison = build_prematch_comparison(canonical_summary, env)
            comparison.update(
                {
                    "fixture_id": fixture_id,
                    "model_id": model.model_id,
                    "model_version": model.model_version,
                    "challenger_freeze_hash": fr.get("freeze_hash"),
                    "canonical_freeze_hash": canonical_summary.get("freeze_hash"),
                }
            )
            save_comparison(conn, comparison)
        return {"prediction": env, "freeze": fr, "comparison": comparison, "diagnostics": diag}
