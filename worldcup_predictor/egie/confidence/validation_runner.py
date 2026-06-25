"""Hold-out validation for hybrid confidence tiers and calibration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.confidence.config import (
    HOLDOUT_TRAIN_RATIO,
    HYBRID_CONFIDENCE_MODEL_VERSION,
    MIN_TIER_SAMPLES,
    SUCCESS_CRITERIA,
    VALIDATION_ARTIFACT_PATH,
)
from worldcup_predictor.egie.confidence.hybrid_engine import HybridConfidenceEngine
from worldcup_predictor.egie.confidence.metrics import (
    expected_calibration_error,
    is_monotonic_tiers,
    tier_accuracy,
)
from worldcup_predictor.egie.confidence.reliability import ReliabilityPriorStore
from worldcup_predictor.egie.confidence.shadow_runner import HybridConfidenceShadowRunner
from worldcup_predictor.egie.confidence.tier_mapper import (
    MarketTierCalibrator,
    TierCalibration,
    fit_market_tier_calibrator,
    fit_tier_calibration,
)
from worldcup_predictor.egie.guards import backtest_mode
from worldcup_predictor.egie.survival.config import SHADOW_PREDICTIONS_PATH
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.evaluation import evaluate_goal_timing_prediction
from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder


def _parse_kickoff(value: str) -> datetime:
    stored = StoredGoalTimingAdapter()
    return stored.parse_kickoff(value) or datetime.min.replace(tzinfo=None)


def _chronological_split(
    records: list[dict[str, Any]],
    *,
    train_ratio: float = HOLDOUT_TRAIN_RATIO,
    stored: StoredGoalTimingAdapter | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    adapter = stored or StoredGoalTimingAdapter()
    pub = [r for r in records if not (r.get("baseline") or {}).get("no_prediction_flag")]

    def sort_key(r: dict[str, Any]) -> datetime:
        fid = int(r.get("fixture_id") or 0)
        target = adapter.get_target_fixture(fid) or {}
        kickoff = adapter.parse_kickoff(str(target.get("kickoff_utc") or ""))
        return kickoff or datetime.min.replace(tzinfo=None)

    pub.sort(key=sort_key)
    cut = max(1, int(len(pub) * train_ratio))
    return pub[:cut], pub[cut:]


class HybridConfidenceValidationRunner:
    """Train tier boundaries on hold-out train; validate monotonicity on test."""

    def __init__(
        self,
        *,
        shadow_runner: HybridConfidenceShadowRunner | None = None,
        source_path: Path | None = None,
    ) -> None:
        self.shadow_runner = shadow_runner or HybridConfidenceShadowRunner()
        self.source_path = source_path or SHADOW_PREDICTIONS_PATH
        self.engine = HybridConfidenceEngine()
        self.stored = self.shadow_runner.stored
        self.feature_builder = self.shadow_runner.feature_builder

    def _score_cohort(
        self,
        records: list[dict[str, Any]],
        *,
        tier_calibration: TierCalibration,
        reliability: ReliabilityPriorStore | None = None,
        team_calibrator: MarketTierCalibrator | None = None,
        range_calibrator: MarketTierCalibrator | None = None,
        minute_calibrator: MarketTierCalibrator | None = None,
    ) -> list[dict[str, Any]]:
        rel = reliability or ReliabilityPriorStore()
        scored: list[dict[str, Any]] = []
        with backtest_mode():
            for rec in records:
                fid = int(rec["fixture_id"])
                comp = str(rec.get("competition_key") or "premier_league")
                target = self.stored.get_target_fixture(fid) or {}
                kickoff = self.stored.parse_kickoff(str(target.get("kickoff_utc") or ""))
                home = str(target.get("home_team") or "")
                away = str(target.get("away_team") or "")
                ctx = {"home_team": home, "away_team": away, "match_date": kickoff}
                features = self.feature_builder.build(fid, competition_key=comp, as_of=kickoff, context=ctx)
                survival_full = self.shadow_runner.survival_runner.survival.predict_fixture(
                    fid, competition_key=comp, as_of=kickoff, context=ctx
                )
                baseline = dict(rec.get("baseline") or {})
                dq = float(baseline.get("data_quality_score") or 0.5)
                result = self.engine.score(
                    fixture_id=fid,
                    competition_key=comp,
                    features=features,
                    baseline=baseline,
                    survival=survival_full,
                    data_quality_score=dq,
                    reliability=rel,
                    tier_calibration=tier_calibration,
                    home_team=home,
                    away_team=away,
                    team_calibrator=team_calibrator,
                    range_calibrator=range_calibrator,
                    minute_calibrator=minute_calibrator,
                )
                act = rec.get("actuals") or {}
                ev = None
                if act:
                    ev = evaluate_goal_timing_prediction(
                        fixture_id=fid,
                        prediction_id=f"val-{fid}",
                        predicted_first_goal_team=baseline.get("first_goal_team"),
                        predicted_first_goal_time_range=baseline.get("first_goal_time_range"),
                        estimated_first_goal_minute=baseline.get("display_estimated_first_goal_minute"),
                        actual_first_goal_team=act.get("actual_first_goal_team"),
                        actual_first_goal_minute=act.get("actual_first_goal_minute"),
                    )
                    team_hit = None if ev.first_goal_team_status == "pending" else int(
                        ev.first_goal_team_status == "correct"
                    )
                    rel.observe(
                        home_team=home,
                        away_team=away,
                        competition_key=comp,
                        team_hit=team_hit,
                        range_hit=int(ev.time_range_status == "correct"),
                    )
                scored.append(
                    {
                        "fixture_id": fid,
                        "hybrid": result.to_dict(),
                        "eval": ev.to_dict() if ev else None,
                    }
                )
        return scored

    def run(self, *, persist_artifact: bool = True) -> dict[str, Any]:
        if not self.source_path.is_file():
            return {"status": "error", "message": f"missing source {self.source_path}"}

        import json as _json

        raw = [_json.loads(l) for l in self.source_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        train_recs, test_recs = _chronological_split(raw, stored=self.stored)

        # Fit tiers on train only
        train_scored = self._score_cohort(
            train_recs,
            tier_calibration=TierCalibration(
                team_q25=0.25, team_q50=0.45, team_q75=0.60,
                range_q25=0.25, range_q50=0.45, range_q75=0.60,
                minute_q25=0.20, minute_q50=0.40, minute_q75=0.55,
            ),
        )
        calibration = fit_tier_calibration(
            [s["hybrid"]["conf_team"] for s in train_scored],
            [s["hybrid"]["conf_range"] for s in train_scored],
            [s["hybrid"]["conf_minute"] for s in train_scored],
        )

        train_team_confs: list[float] = []
        train_team_hits: list[int] = []
        train_range_confs: list[float] = []
        train_range_hits: list[int] = []
        train_minute_confs: list[float] = []
        train_minute_hits: list[int] = []
        for s in train_scored:
            ev = s.get("eval")
            if not ev:
                continue
            h = s["hybrid"]
            if ev.get("first_goal_team_status") != "pending":
                train_team_confs.append(h["conf_team"])
                train_team_hits.append(1 if ev.get("first_goal_team_status") == "correct" else 0)
            train_range_confs.append(h["conf_range"])
            train_range_hits.append(1 if ev.get("time_range_status") == "correct" else 0)
            train_minute_confs.append(h["conf_minute"])
            train_minute_hits.append(
                1 if ev.get("minute_tolerance_status") in ("correct", "partial") else 0
            )

        team_calibrator = fit_market_tier_calibrator(train_team_confs, train_team_hits, market="team")
        range_calibrator = fit_market_tier_calibrator(train_range_confs, train_range_hits, market="range")
        minute_calibrator = fit_market_tier_calibrator(train_minute_confs, train_minute_hits, market="minute")

        test_scored = self._score_cohort(
            test_recs,
            tier_calibration=calibration,
            team_calibrator=team_calibrator,
            range_calibrator=range_calibrator,
            minute_calibrator=minute_calibrator,
        )

        # Outcome extraction
        def extract_market(scored: list[dict[str, Any]], market: str) -> tuple[list[str], list[float], list[int]]:
            tiers: list[str] = []
            confs: list[float] = []
            hits: list[int] = []
            for s in scored:
                ev = s.get("eval")
                if not ev:
                    continue
                h = s["hybrid"]
                if market == "team":
                    if ev.get("first_goal_team_status") == "pending":
                        continue
                    tiers.append(h["tiers"]["team_tier"])
                    confs.append(h["conf_team"])
                    hits.append(1 if ev.get("first_goal_team_status") == "correct" else 0)
                elif market == "range":
                    tiers.append(h["tiers"]["range_tier"])
                    confs.append(h["conf_range"])
                    hits.append(1 if ev.get("time_range_status") == "correct" else 0)
                else:
                    tiers.append(h["tiers"]["minute_tier"])
                    confs.append(h["conf_minute"])
                    hits.append(
                        1 if ev.get("minute_tolerance_status") in ("correct", "partial") else 0
                    )
            return tiers, confs, hits

        team_tiers, team_confs, team_hits = extract_market(test_scored, "team")
        range_tiers, range_confs, range_hits = extract_market(test_scored, "range")
        minute_tiers, minute_confs, minute_hits = extract_market(test_scored, "minute")

        team_tier_stats = tier_accuracy(team_tiers, team_hits)
        range_tier_stats = tier_accuracy(range_tiers, range_hits)
        minute_tier_stats = tier_accuracy(minute_tiers, minute_hits)

        team_mono = is_monotonic_tiers(team_tier_stats, min_samples=MIN_TIER_SAMPLES)
        range_mono = is_monotonic_tiers(range_tier_stats, min_samples=MIN_TIER_SAMPLES)
        minute_mono = is_monotonic_tiers(minute_tier_stats, min_samples=MIN_TIER_SAMPLES)

        legacy_confs = [
            float((r.get("baseline") or {}).get("confidence_score") or 0.65)
            for r in test_recs
            if r.get("actuals")
        ]
        legacy_team_hits = team_hits  # same fixtures
        legacy_range_hits = range_hits

        legacy_ece_team = expected_calibration_error(legacy_confs[: len(team_hits)], team_hits)
        legacy_ece_range = expected_calibration_error(legacy_confs[: len(range_hits)], range_hits)
        hybrid_ece_team = expected_calibration_error(team_confs, team_hits)
        hybrid_ece_range = expected_calibration_error(range_confs, range_hits)

        legacy_dist = [
            float((r.get("baseline") or {}).get("confidence_score") or 0.65)
            for r in raw
            if not (r.get("baseline") or {}).get("no_prediction_flag")
        ]

        def dist_summary(vals: list[float]) -> dict[str, Any]:
            if not vals:
                return {}
            ordered = sorted(vals)
            return {
                "min": round(min(vals), 4),
                "max": round(max(vals), 4),
                "mean": round(sum(vals) / len(vals), 4),
                "p25": round(ordered[len(ordered) // 4], 4),
                "p50": round(ordered[len(ordered) // 2], 4),
                "p75": round(ordered[3 * len(ordered) // 4], 4),
                "at_0_65_pct": round(100 * sum(1 for v in vals if abs(v - 0.65) < 0.001) / len(vals), 2),
            }

        monotonic_pass = team_mono and range_mono
        deploy_allowed = monotonic_pass and (
            (hybrid_ece_team or 1.0) <= SUCCESS_CRITERIA["ece_team_max"]
            and (hybrid_ece_range or 1.0) <= SUCCESS_CRITERIA["ece_range_max"]
        )

        isotonic_payload: dict[str, Any] = {}
        if team_calibrator:
            isotonic_payload["team"] = team_calibrator.to_dict()
        if range_calibrator:
            isotonic_payload["range"] = range_calibrator.to_dict()
        if minute_calibrator:
            isotonic_payload["minute"] = minute_calibrator.to_dict()

        all_scored = self._score_cohort(
            [r for r in raw if not (r.get("baseline") or {}).get("no_prediction_flag")],
            tier_calibration=calibration,
            team_calibrator=team_calibrator,
            range_calibrator=range_calibrator,
            minute_calibrator=minute_calibrator,
        )
        conf_team_dist = [s["hybrid"]["conf_team"] for s in all_scored]
        conf_range_dist = [s["hybrid"]["conf_range"] for s in all_scored]

        payload: dict[str, Any] = {
            "phase": "52D",
            "phase_52d_status": "PRODUCTION_ACTIVE" if deploy_allowed else "SHADOW_VALIDATED",
            "model_version": HYBRID_CONFIDENCE_MODEL_VERSION,
            "shadow_mode_only": not deploy_allowed,
            "production_active": deploy_allowed,
            "cohort": {
                "total_fixtures": len(raw),
                "published": len([r for r in raw if not (r.get("baseline") or {}).get("no_prediction_flag")]),
                "train_size": len(train_recs),
                "test_size": len(test_recs),
                "holdout_train_ratio": HOLDOUT_TRAIN_RATIO,
            },
            "tier_calibration": calibration.to_dict(),
            "isotonic_calibrators": isotonic_payload,
            "holdout_test": {
                "team": {
                    "tier_stats": team_tier_stats,
                    "monotonic": team_mono,
                    "ece_legacy": legacy_ece_team,
                    "ece_hybrid": hybrid_ece_team,
                },
                "range": {
                    "tier_stats": range_tier_stats,
                    "monotonic": range_mono,
                    "ece_legacy": legacy_ece_range,
                    "ece_hybrid": hybrid_ece_range,
                },
                "minute": {
                    "tier_stats": minute_tier_stats,
                    "monotonic": minute_mono,
                    "experimental": True,
                },
            },
            "monotonicity": {
                "team": team_mono,
                "range": range_mono,
                "minute": minute_mono,
                "overall_pass": monotonic_pass,
                "required": SUCCESS_CRITERIA["monotonic_tiers_required"],
            },
            "distribution": {
                "legacy_confidence": dist_summary(legacy_dist),
                "conf_team": dist_summary(conf_team_dist),
                "conf_range": dist_summary(conf_range_dist),
            },
            "success_criteria": SUCCESS_CRITERIA,
            "deploy_allowed": deploy_allowed,
            "deploy_rule": "Deploy only if confidence tiers are monotonic on hold-out test",
        }

        if persist_artifact:
            VALIDATION_ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
            VALIDATION_ARTIFACT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        return payload
