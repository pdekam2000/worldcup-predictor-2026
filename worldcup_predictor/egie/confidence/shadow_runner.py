"""Run hybrid confidence alongside baseline/survival shadow predictions."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.confidence.config import TIER_CALIBRATION_PATH, VALIDATION_ARTIFACT_PATH
from worldcup_predictor.egie.confidence.hybrid_engine import HybridConfidenceEngine
from worldcup_predictor.egie.confidence.reliability import ReliabilityPriorStore
from worldcup_predictor.egie.confidence.shadow_store import HybridConfidenceShadowStore
from worldcup_predictor.egie.confidence.tier_mapper import MarketTierCalibrator, TierCalibration, fit_tier_calibration
from worldcup_predictor.egie.guards import backtest_mode
from worldcup_predictor.egie.survival.config import SHADOW_PREDICTIONS_PATH
from worldcup_predictor.egie.survival.shadow_runner import SurvivalShadowRunner
from worldcup_predictor.egie.survival.survival_engine import SurvivalGoalTimingEngine
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.engine import EliteGoalTimingEngine
from worldcup_predictor.goal_timing.evaluation import evaluate_goal_timing_prediction
from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder

logger = logging.getLogger(__name__)


def _load_isotonic_calibrators() -> tuple[MarketTierCalibrator | None, MarketTierCalibrator | None, MarketTierCalibrator | None]:
    if not VALIDATION_ARTIFACT_PATH.is_file():
        return None, None, None
    payload = json.loads(VALIDATION_ARTIFACT_PATH.read_text(encoding="utf-8"))
    iso = payload.get("isotonic_calibrators") or {}
    team = MarketTierCalibrator.from_dict(iso["team"]) if iso.get("team") else None
    rng = MarketTierCalibrator.from_dict(iso["range"]) if iso.get("range") else None
    minute = MarketTierCalibrator.from_dict(iso["minute"]) if iso.get("minute") else None
    return team, rng, minute


class HybridConfidenceShadowRunner:
    """Attach per-market hybrid confidence to EGIE shadow predictions."""

    def __init__(
        self,
        *,
        survival_runner: SurvivalShadowRunner | None = None,
        confidence_engine: HybridConfidenceEngine | None = None,
        store: HybridConfidenceShadowStore | None = None,
        stored: StoredGoalTimingAdapter | None = None,
    ) -> None:
        self.survival_runner = survival_runner or SurvivalShadowRunner()
        self.confidence_engine = confidence_engine or HybridConfidenceEngine()
        self.store = store or HybridConfidenceShadowStore()
        self.stored = stored or self.survival_runner.baseline.feature_builder.stored
        self.feature_builder = self.survival_runner.baseline.feature_builder

    def run_from_survival_jsonl(
        self,
        *,
        source_path: Path | None = None,
        persist: bool = True,
        tier_calibration: TierCalibration | None = None,
    ) -> list[dict[str, Any]]:
        """Replay hybrid confidence over existing survival shadow records."""
        path = source_path or SHADOW_PREDICTIONS_PATH
        if not path.is_file():
            return []
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        return self.run_records(rows, persist=persist, tier_calibration=tier_calibration)

    def run_records(
        self,
        survival_records: list[dict[str, Any]],
        *,
        persist: bool = True,
        tier_calibration: TierCalibration | None = None,
    ) -> list[dict[str, Any]]:
        pub = [r for r in survival_records if not (r.get("baseline") or {}).get("no_prediction_flag")]
        if not pub:
            return []

        # Pass 1: score all without tiers to fit calibration if needed
        reliability = ReliabilityPriorStore()
        scored_rows: list[dict[str, Any]] = []

        with backtest_mode():
            for rec in pub:
                fid = int(rec["fixture_id"])
                comp = str(rec.get("competition_key") or "premier_league")
                target = self.stored.get_target_fixture(fid) or {}
                kickoff = self.stored.parse_kickoff(str(target.get("kickoff_utc") or ""))
                home = str(target.get("home_team") or "")
                away = str(target.get("away_team") or "")
                ctx = {"home_team": home, "away_team": away, "match_date": kickoff}
                features = self.feature_builder.build(fid, competition_key=comp, as_of=kickoff, context=ctx)

                survival_eng = self.survival_runner.survival
                survival_full = survival_eng.predict_fixture(fid, competition_key=comp, as_of=kickoff, context=ctx)
                baseline = dict(rec.get("baseline") or {})
                baseline["match_first_goal_range_probs"] = (
                    survival_full.get("range_probabilities")
                    or baseline.get("match_first_goal_range_probs")
                    or {}
                )

                dq = float(baseline.get("data_quality_score") or survival_full.get("data_quality_score") or 0.5)
                neutral_cal = tier_calibration or TierCalibration(
                    team_q25=0.25, team_q50=0.45, team_q75=0.60,
                    range_q25=0.25, range_q50=0.45, range_q75=0.60,
                    minute_q25=0.20, minute_q50=0.40, minute_q75=0.55,
                )
                result = self.confidence_engine.score(
                    fixture_id=fid,
                    competition_key=comp,
                    features=features,
                    baseline=baseline,
                    survival=survival_full,
                    data_quality_score=dq,
                    reliability=reliability,
                    tier_calibration=neutral_cal,
                    home_team=home,
                    away_team=away,
                )
                scored_rows.append({"rec": rec, "result": result, "features": features, "survival_full": survival_full})

                act = rec.get("actuals") or {}
                if act:
                    ev = evaluate_goal_timing_prediction(
                        fixture_id=fid,
                        prediction_id=f"hybrid-{fid}",
                        predicted_first_goal_team=baseline.get("first_goal_team"),
                        predicted_first_goal_time_range=baseline.get("first_goal_time_range"),
                        estimated_first_goal_minute=baseline.get("display_estimated_first_goal_minute"),
                        actual_first_goal_team=act.get("actual_first_goal_team"),
                        actual_first_goal_minute=act.get("actual_first_goal_minute"),
                    )
                    team_hit = None if ev.first_goal_team_status == "pending" else int(
                        ev.first_goal_team_status == "correct"
                    )
                    reliability.observe(
                        home_team=home,
                        away_team=away,
                        competition_key=comp,
                        team_hit=team_hit,
                        range_hit=int(ev.time_range_status == "correct"),
                    )

        if tier_calibration is None:
            tier_calibration = fit_tier_calibration(
                [s["result"].scores.conf_team for s in scored_rows],
                [s["result"].scores.conf_range for s in scored_rows],
                [s["result"].scores.conf_minute for s in scored_rows],
            )
            TIER_CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
            TIER_CALIBRATION_PATH.write_text(
                json.dumps(tier_calibration.to_dict(), indent=2),
                encoding="utf-8",
            )

        team_cal, range_cal, minute_cal = _load_isotonic_calibrators()

        # Pass 2: re-score with fitted tiers (reliability still rolling — refit from scratch)
        reliability2 = ReliabilityPriorStore()
        out: list[dict[str, Any]] = []
        with backtest_mode():
            for item in scored_rows:
                rec = item["rec"]
                fid = int(rec["fixture_id"])
                comp = str(rec.get("competition_key") or "premier_league")
                target = self.stored.get_target_fixture(fid) or {}
                kickoff = self.stored.parse_kickoff(str(target.get("kickoff_utc") or ""))
                home = str(target.get("home_team") or "")
                away = str(target.get("away_team") or "")
                baseline = dict(rec.get("baseline") or {})
                dq = float(baseline.get("data_quality_score") or 0.5)
                result = self.confidence_engine.score(
                    fixture_id=fid,
                    competition_key=comp,
                    features=item["features"],
                    baseline=baseline,
                    survival=item["survival_full"],
                    data_quality_score=dq,
                    reliability=reliability2,
                    tier_calibration=tier_calibration,
                    home_team=home,
                    away_team=away,
                    team_calibrator=team_cal,
                    range_calibrator=range_cal,
                    minute_calibrator=minute_cal,
                )
                act = rec.get("actuals") or {}
                if act:
                    ev = evaluate_goal_timing_prediction(
                        fixture_id=fid,
                        prediction_id=f"hybrid-{fid}",
                        predicted_first_goal_team=baseline.get("first_goal_team"),
                        predicted_first_goal_time_range=baseline.get("first_goal_time_range"),
                        estimated_first_goal_minute=baseline.get("display_estimated_first_goal_minute"),
                        actual_first_goal_team=act.get("actual_first_goal_team"),
                        actual_first_goal_minute=act.get("actual_first_goal_minute"),
                    )
                    team_hit = None if ev.first_goal_team_status == "pending" else int(
                        ev.first_goal_team_status == "correct"
                    )
                    reliability2.observe(
                        home_team=home,
                        away_team=away,
                        competition_key=comp,
                        team_hit=team_hit,
                        range_hit=int(ev.time_range_status == "correct"),
                    )

                record = {
                    "fixture_id": fid,
                    "competition_key": comp,
                    "kickoff_utc": str(target.get("kickoff_utc") or ""),
                    "baseline": rec.get("baseline"),
                    "survival": rec.get("survival"),
                    "hybrid_confidence": result.to_dict(),
                    "actuals": act,
                }
                if rec.get("baseline_eval"):
                    record["baseline_eval"] = rec["baseline_eval"]
                out.append(record)

        if persist:
            self.store.write_all(out)
        return out

    def run_fixture(
        self,
        fixture_id: int,
        *,
        competition_key: str,
        as_of: datetime | None = None,
        context: dict[str, Any] | None = None,
        actuals: dict[str, Any] | None = None,
        tier_calibration: TierCalibration | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        shadow = self.survival_runner.run_fixture(
            fixture_id,
            competition_key=competition_key,
            as_of=as_of,
            context=context,
            actuals=actuals,
            persist=False,
        )
        records = self.run_records([shadow], persist=False, tier_calibration=tier_calibration)
        record = records[0] if records else shadow
        if persist:
            self.store.append(record)
        return record
