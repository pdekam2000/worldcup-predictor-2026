"""Build chronological historical betting-day dataset — research-only."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.phase5.corpus import build_phase5_corpus
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.constants import BASELINE_POLICY
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.policy_engine import (
    decide_under_policy,
    group_days,
    league_reliability,
)
from worldcup_predictor.research.betting_day_similarity.feature_builder import (
    build_day_feature_vector,
    compute_day_labels,
    expected_feature_names,
    rolling_stats_before_date,
)


def _load_calibrated_policy() -> dict[str, Any]:
    path = Path("worldcup_predictor/research/bet_portfolio_manager/calibrated_policy_candidate.json")
    if not path.exists():
        return copy.deepcopy(BASELINE_POLICY)
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Reconstruct a runnable policy dict without mutating the stored file
    pol = copy.deepcopy(BASELINE_POLICY)
    pol["policy_version"] = raw.get("policy_version") or "calibrated_candidate"
    if raw.get("locked_thresholds"):
        pol["action_thresholds"] = dict(raw["locked_thresholds"])
    if raw.get("grade_boundaries"):
        pol["grade_thresholds"] = dict(raw["grade_boundaries"])
    if raw.get("gates"):
        pol["gates"] = dict(raw["gates"])
    pol["watch_micro_allocation_ratio"] = float(raw.get("micro_allocation_ratio") or 0.0)
    pol["watch_positive_score_slack"] = 6.0
    return pol


def build_historical_day_dataset(
    *,
    fixtures: list[dict[str, Any]] | None = None,
    max_historical: int = 1200,
    lookback_days: int = 90,
) -> dict[str, Any]:
    if fixtures is None:
        corpus = build_phase5_corpus(min_fixtures=min(600, max_historical), max_historical=max_historical, top_n=8)
        fixtures = list(corpus.get("primary_fixtures") or [])[:max_historical]

    days_map = group_days(fixtures)
    lr = league_reliability(fixtures)
    baseline = BASELINE_POLICY
    calibrated = _load_calibrated_policy()

    # First pass: decisions + provisional features without rolling
    provisional: list[dict[str, Any]] = []
    for date, rows in days_map.items():
        bdec = decide_under_policy(rows, policy=baseline, league_reliability_map=lr)
        cdec = decide_under_policy(rows, policy=calibrated, league_reliability_map=lr)
        cutoff = f"{date}T12:00:00Z"
        feat_pack = build_day_feature_vector(
            rows,
            date=date,
            cutoff_timestamp=cutoff,
            rolling_stats=None,
            baseline_decision=bdec,
            calibrated_decision=cdec,
        )
        labels = compute_day_labels(rows, bdec)
        provisional.append(
            {
                "day_id": feat_pack["meta"]["day_id"],
                "vienna_date": date,
                "date": date,
                "cutoff_timestamp": cutoff,
                "features": feat_pack["features"],
                "meta": feat_pack["meta"],
                "baseline_action": bdec.get("action"),
                "calibrated_action": cdec.get("action"),
                "baseline_selected_fixture_ids": list(bdec.get("selected_fixture_ids") or []),
                "calibrated_selected_fixture_ids": list(cdec.get("selected_fixture_ids") or []),
                "baseline_exposure": float(bdec.get("exposure_units") or 0),
                "calibrated_exposure": float(cdec.get("exposure_units") or 0),
                "main_ticket_count": len(bdec.get("selected_fixture_ids") or []),
                "insurance_ticket_count": len(bdec.get("selected_fixture_ids") or []),
                "allocated_capital": float(bdec.get("exposure_units") or 0),
                "labels": labels,
                "input_hash": feat_pack["meta"]["feature_content_hash"],
                "label_hash": labels.get("label_hash"),
                "fixtures": rows,
            }
        )

    # Second pass: inject rolling features excluding current/future
    final_days = []
    for d in provisional:
        rolling = rolling_stats_before_date(provisional, target_date=d["vienna_date"], lookback_days=lookback_days)
        feats = dict(d["features"])
        feats.update(rolling)
        # re-hash features after rolling injection
        feats_hash = hashlib.sha256(
            json.dumps(feats, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        nd = dict(d)
        nd["features"] = feats
        nd["input_hash"] = feats_hash
        nd["meta"] = {**d["meta"], "feature_content_hash": feats_hash}
        final_days.append(nd)

    feature_names = expected_feature_names()
    manifest = {
        "research_only": True,
        "n_days": len(final_days),
        "n_fixtures": len(fixtures),
        "feature_count": len(feature_names),
        "feature_names": feature_names,
        "date_range": [final_days[0]["vienna_date"], final_days[-1]["vienna_date"]] if final_days else [],
        "lookback_days": lookback_days,
        "baseline_policy": baseline.get("policy_version"),
        "calibrated_policy": calibrated.get("policy_version"),
        "labels_separated": True,
    }
    return {"days": final_days, "manifest": manifest, "feature_names": feature_names}
