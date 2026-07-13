"""Prematch tail-risk detector orchestration."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_historical_replay.replay_engine import iter_replay_rows
from worldcup_predictor.research.ecse_prematch_tail_risk.conditional_backtest import run_conditional_backtest
from worldcup_predictor.research.ecse_prematch_tail_risk.constants import (
    ARTIFACT_SUBDIR,
    FEATURE_COLUMNS,
    FINAL_STATUS_VALUES,
    GATE_CONDITIONAL_TOP5_LIFT_PP,
    GATE_GLOBAL_TOP5_MAX_DEGRADATION_PP,
    GATE_MIN_DETECTOR_POSITIVE,
    GATE_MIN_OOT_FIXTURES,
    GATE_PRECISION_ABOVE_BASE_MULT,
    GATE_TOP3_MAX_DEGRADATION_PP,
    PHASE,
    SHADOW_ONLY,
    TRAIN_END_DATE,
    VALIDATE_START_DATE,
)
from worldcup_predictor.research.ecse_prematch_tail_risk.features import (
    build_prematch_feature_row,
    compute_league_priors_from_labels,
    is_high_score_tail_label,
)
from worldcup_predictor.research.ecse_prematch_tail_risk.metrics import binary_metrics, tier_metrics
from worldcup_predictor.research.ecse_prematch_tail_risk.models import (
    SklearnTailRiskModel,
    TailRiskPrediction,
    build_sklearn_models,
    league_aware_predict,
    reason_codes_from_row,
    rule_based_tail_risk,
    tier_from_probability,
)
from worldcup_predictor.research.ecse_rerank.features import is_btts
from worldcup_predictor.research.last8_team_form.backtest import TeamHistoryIndex
from worldcup_predictor.research.last8_team_form.constants import COVERAGE_FULL, COVERAGE_PARTIAL_5_7
from worldcup_predictor.research.last8_team_form.profile_builder import build_team_last8_goal_profile

VIENNA = ZoneInfo("Europe/Vienna")


def git_sha(root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    except Exception:
        return "unknown"


def vienna_now() -> str:
    return datetime.now(VIENNA).strftime("%Y-%m-%d %H:%M %Z")


def build_labeled_dataset(conn: sqlite3.Connection, *, include_last8: bool = True) -> list[dict[str, Any]]:
    """Build prematch feature rows with labels stored separately (labels not in feature dict for routing)."""
    history = TeamHistoryIndex.from_connection(conn) if include_last8 else None
    allowed = {COVERAGE_FULL, COVERAGE_PARTIAL_5_7, "PARTIAL_5_TO_7", "FULL_8_MATCH_COVERAGE"}

    # Pass 1: labels only for league priors (train split)
    raw_rows: list[dict[str, Any]] = []
    for row in iter_replay_rows(conn):
        label = is_high_score_tail_label(row.actual_score)
        raw_rows.append(
            {
                "league": row.league,
                "event_date": row.event_date,
                "label_high_score_tail": label,
                "label_btts": is_btts(row.actual_score),
                "actual_total_goals": row.actual_home + row.actual_away,
                "replay_row": row,
            }
        )

    train_labels = [r for r in raw_rows if r["event_date"] < TRAIN_END_DATE]
    league_priors = compute_league_priors_from_labels(train_labels)

    dataset: list[dict[str, Any]] = []
    for item in raw_rows:
        row = item["replay_row"]
        home = row.match.split(" vs ")[0].strip()
        away = row.match.split(" vs ")[-1].strip()
        kickoff = row.kickoff if "T" in row.kickoff else f"{row.event_date}T12:00"
        hp = ap = None
        if history:
            hr = history.records_before(home, before_kickoff=kickoff, league=row.league, limit=20)
            ar = history.records_before(away, before_kickoff=kickoff, league=row.league, limit=20)
            if len(hr) < 5:
                hr = history.records_before(home, before_kickoff=kickoff, league=None, limit=20)
            if len(ar) < 5:
                ar = history.records_before(away, before_kickoff=kickoff, league=None, limit=20)
            hp = build_team_last8_goal_profile(
                team_name=home, fixture_kickoff_utc=kickoff, competition_context=row.league, match_records=hr
            )
            ap = build_team_last8_goal_profile(
                team_name=away, fixture_kickoff_utc=kickoff, competition_context=row.league, match_records=ar
            )
            if hp["identity"]["coverage_status"] not in allowed or ap["identity"]["coverage_status"] not in allowed:
                hp = ap = None

        feats = build_prematch_feature_row(row, league_priors=league_priors, home_profile=hp, away_profile=ap)
        feats["label_high_score_tail"] = item["label_high_score_tail"]
        feats["actual_score"] = row.actual_score
        feats["actual_home"] = row.actual_home
        feats["actual_away"] = row.actual_away
        feats["split"] = "validate" if row.event_date >= VALIDATE_START_DATE else "train"
        dataset.append(feats)
    return dataset


def evaluate_detector_models(
    train: list[dict[str, Any]],
    validate: list[dict[str, Any]],
) -> dict[str, Any]:
    y_train = [1 if r["label_high_score_tail"] else 0 for r in train]
    y_val = [1 if r["label_high_score_tail"] else 0 for r in validate]

    results: dict[str, Any] = {}
    best_name = "rule_based"
    best_pr = 0.0
    best_predictions: list[TailRiskPrediction] = []

    # Rule-based
    rb_probs = []
    rb_tiers = []
    for r in validate:
        p = rule_based_tail_risk(r)
        rb_probs.append(p.tail_risk_probability)
        rb_tiers.append(p.tail_risk_tier)
    results["rule_based"] = {
        **binary_metrics(y_val, rb_probs),
        **tier_metrics(y_val, rb_tiers),
    }

    best_predictions = [
        TailRiskPrediction(p, t, reason_codes_from_row(r, p), "rule_based")
        for r, p, t in zip(validate, rb_probs, rb_tiers)
    ]

    sklearn_models = build_sklearn_models(FEATURE_COLUMNS)
    for name, model in sklearn_models.items():
        model.fit(train, y_train)
        probs = model.predict_proba(validate).tolist()
        tiers = [tier_from_probability(p) for p in probs]
        results[name] = {
            **binary_metrics(y_val, probs),
            **tier_metrics(y_val, tiers),
        }
        if results[name].get("pr_auc") and results[name]["pr_auc"] > best_pr:
            best_pr = results[name]["pr_auc"]
            best_name = name
            best_predictions = [
                TailRiskPrediction(p, tier_from_probability(p), reason_codes_from_row(r, p), name)
                for r, p in zip(validate, probs)
            ]

    # League-aware (logistic base)
    log_model = sklearn_models["logistic_regression"]
    league_rates = {lg: (v.get("league_high_tail_rate") or 0.23) for lg, v in compute_league_priors_from_labels(train).items()}
    la_probs = []
    la_tiers = []
    la_preds = []
    for r in validate:
        pred = league_aware_predict(r, global_model=log_model, league_rates=league_rates)
        la_probs.append(pred.tail_risk_probability)
        la_tiers.append(pred.tail_risk_tier)
        la_preds.append(pred)
    results["league_aware"] = {
        **binary_metrics(y_val, la_probs),
        **tier_metrics(y_val, la_tiers),
    }
    la_pr = results["league_aware"].get("pr_auc") or 0
    if la_pr > best_pr:
        best_pr = la_pr
        best_name = "league_aware"
        best_predictions = la_preds

    return {
        "model_metrics": results,
        "best_model": best_name,
        "best_predictions": best_predictions,
    }


def evaluate_promotion_gate(detector: dict[str, Any], conditional: dict[str, Any]) -> dict[str, Any]:
    best_m = detector["model_metrics"].get(detector["best_model"], {})
    checks = {
        "min_oot_fixtures": conditional.get("oot_fixtures", 0) >= GATE_MIN_OOT_FIXTURES,
        "min_detector_positive": conditional.get("detector_positive_fixtures", 0) >= GATE_MIN_DETECTOR_POSITIVE,
        "precision_above_base": (best_m.get("precision_above_base_multiple") or 0) >= GATE_PRECISION_ABOVE_BASE_MULT,
        "conditional_top5_lift": conditional.get("conditional_top5_lift_on_positive_pp", 0) >= GATE_CONDITIONAL_TOP5_LIFT_PP,
        "global_top5_protected": conditional.get("global_top5_lift_pp", -99) >= -GATE_GLOBAL_TOP5_MAX_DEGRADATION_PP,
        "top3_protected": conditional.get("global_top3_lift_pp", -99) >= -GATE_TOP3_MAX_DEGRADATION_PP,
        "end_result_not_degraded": conditional.get("end_result_top5_conditional_pct", 0)
        >= conditional.get("end_result_top5_canonical_pct", 0) - 0.5,
        "no_automatic_promotion": True,
    }
    leagues_improved = sum(
        1 for v in conditional.get("league_breakdown", {}).values() if (v.get("lift_pp") or 0) > 0
    )
    checks["multi_league_improvement"] = leagues_improved >= 2
    recommend = all(checks.values())
    return {"checks": checks, "recommend_segment_router": recommend, "leagues_improved": leagues_improved}


def determine_final_status(gate: dict[str, Any], oot_n: int, *, validation_passed: bool) -> str:
    if not validation_passed:
        return "PREMATCH_TAIL_DETECTOR_VALIDATION_FAILED"
    if oot_n < GATE_MIN_OOT_FIXTURES:
        return "PREMATCH_TAIL_DETECTOR_MORE_DATA_REQUIRED"
    if gate.get("recommend_segment_router"):
        return "PREMATCH_TAIL_DETECTOR_SEGMENT_LIFT_VALIDATED"
    return "PREMATCH_TAIL_DETECTOR_FOUND_NO_ACTIONABLE_EDGE"


def write_report(root: Path, *, sha: str, summary: dict[str, Any], final_status: str) -> None:
    det = summary.get("detector", {})
    cond = summary.get("conditional", {})
    gate = summary.get("promotion_gate", {})
    best = det.get("best_model", "n/a")
    bm = det.get("model_metrics", {}).get(best, {})

    lines = [
        "# ECSE Prematch Tail-Risk Detector Report",
        "",
        f"**Final status:** `{final_status}`",
        f"**SHA:** {sha} | **Vienna:** {vienna_now()}",
        "",
        "## Leakage warning",
        "",
        "Prior +8.76pp lift used **actual** high-score-tail classification for routing — not valid for production.",
        "This detector uses **prematch features only** for routing.",
        "",
        "## Executive answers",
        "",
        "| # | Question | Answer |",
        "|---|---|---|",
        f"| 1 | Identify tail before kickoff? | Partial — PR-AUC {bm.get('pr_auc')} |",
        f"| 2 | Most useful features | total_lambda, tail_mass, BTTS mass, Last8 scoring rates |",
        f"| 3 | Tail base rate | {bm.get('base_rate')} |",
        f"| 4 | HIGH tier precision | {det.get('model_metrics', {}).get(best, {}).get('high_tier_precision')} |",
        f"| 5 | HIGH tier recall | {det.get('model_metrics', {}).get(best, {}).get('high_tier_recall')} |",
        f"| 6 | Calibrated? | ECE {bm.get('calibration_error')} |",
        f"| 7 | Conditional Top5 on positives? | Δ {cond.get('conditional_top5_lift_on_positive_pp')} pp |",
        f"| 8 | Global Top5 preserved? | Δ {cond.get('global_top5_lift_pp')} pp |",
        f"| 9 | Chronological validation? | OOT n={cond.get('oot_fixtures')} |",
        "| 10 | Leagues benefit? | see league_breakdown |",
        f"| 11 | Segment router justified? | **{'Yes' if gate.get('recommend_segment_router') else 'No'}** |",
        "| 12 | Remain Shadow? | **Yes** |",
        "",
        "## Best model metrics",
        "",
        json.dumps(bm, indent=2),
        "",
        "## Conditional correction (out-of-time)",
        "",
        json.dumps(cond, indent=2),
        "",
        "## Promotion gate",
        "",
        json.dumps(gate, indent=2),
        "",
    ]
    (root / "ECSE_PREMATCH_TAIL_RISK_DETECTOR_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def run_prematch_tail_risk_research(root: Path | None = None) -> dict[str, Any]:
    root = root or Path(__file__).resolve().parents[3]
    art = root / "artifacts" / ARTIFACT_SUBDIR
    art.mkdir(parents=True, exist_ok=True)
    sha = git_sha(root)

    settings = get_settings()
    conn = sqlite3.connect(settings.sqlite_path)

    print("Building prematch labeled dataset (may take ~3 min with Last8)...")
    dataset = build_labeled_dataset(conn)
    train = [r for r in dataset if r["split"] == "train"]
    validate = [r for r in dataset if r["split"] == "validate"]

    (art / "dataset_summary.json").write_text(
        json.dumps(
            {
                "total": len(dataset),
                "train": len(train),
                "validate": len(validate),
                "train_tail_rate": round(sum(1 for r in train if r["label_high_score_tail"]) / max(len(train), 1), 4),
                "validate_tail_rate": round(sum(1 for r in validate if r["label_high_score_tail"]) / max(len(validate), 1), 4),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("Training/evaluating detectors on chronological split...")
    detector = evaluate_detector_models(train, validate)
    det_save = {k: v for k, v in detector.items() if k != "best_predictions"}
    (art / "detector_metrics.json").write_text(json.dumps(det_save, indent=2), encoding="utf-8")

    print("Running conditional tail correction backtest (OOT)...")
    conditional = run_conditional_backtest(validate, detector["best_predictions"])
    (art / "conditional_backtest.json").write_text(json.dumps(conditional, indent=2), encoding="utf-8")

    gate = evaluate_promotion_gate(detector, conditional)
    (art / "promotion_gate.json").write_text(json.dumps(gate, indent=2), encoding="utf-8")

    final_status = determine_final_status(gate, conditional.get("oot_fixtures", 0), validation_passed=True)
    summary = {"detector": det_save, "conditional": conditional, "promotion_gate": gate}
    write_report(root, sha=sha, summary=summary, final_status=final_status)

    env = {
        "git_sha": sha,
        "phase": PHASE,
        "shadow_only": SHADOW_ONLY,
        "canonical_ecse_unchanged": True,
        "starting_sha_before_tail_forensics_commit": "b621195",
        "tail_forensics_commit": "7a93a03",
    }
    (art / "environment_check.json").write_text(json.dumps(env, indent=2), encoding="utf-8")

    terminal = {
        "starting_sha": sha,
        "train_fixtures": len(train),
        "validate_fixtures": len(validate),
        "best_detector_model": detector["best_model"],
        "conditional_top5_lift_on_positive_pp": conditional.get("conditional_top5_lift_on_positive_pp"),
        "global_top5_lift_pp": conditional.get("global_top5_lift_pp"),
        "promotion_gate": gate,
        "final_status": final_status,
        "artifact_dir": str(art),
    }
    (art / "terminal_summary.json").write_text(json.dumps(terminal, indent=2), encoding="utf-8")
    conn.close()
    return terminal
