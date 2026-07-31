"""Threshold calibration pipeline — research-only orchestration."""

from __future__ import annotations

import copy
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.phase5.corpus import build_phase5_corpus
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.audits import (
    action_performance_audit,
    action_semantics_audit,
    gate_attribution,
    grade_audit,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.capital_modes import (
    calibrate_capital_modes,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.constants import (
    BASELINE_COMMIT,
    BASELINE_POLICY,
    PHASE_NAME,
    STATUS_COMPLETE,
    STATUS_HOLD,
    STATUS_RESEARCH_MORE,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.forward_compare import (
    SCHEMA as FORWARD_SCHEMA,
    compare_forward_days,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.grid_search import (
    check_guardrails,
    chronological_splits,
    evaluate_policy_on_fixtures,
    generate_candidate_policies,
    leakage_validation,
    pareto_frontier,
    run_grid_on_split,
    score_candidate,
    walk_forward_folds,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.metrics import (
    always_bet_metrics,
    summarize_days,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.policy_engine import (
    league_reliability,
    replay_all_days,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.watch_split import (
    research_watch_split,
)


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _write_md(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _strip_fixtures(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop bulky fixture payloads for artifact rows."""
    out = []
    for d in days:
        row = {k: v for k, v in d.items() if k != "fixtures"}
        out.append(row)
    return out


def _grid_row(r: dict[str, Any]) -> dict[str, Any]:
    vm = r["validation_metrics"]
    staked = float(vm.get("total_staked") or 0)
    pnl = float(vm.get("net_return") or 0)
    wins = int(vm.get("wins") or 0)
    losses = int(vm.get("losses") or 0)
    n = max(1, int(vm.get("n_days") or 1))
    downside = abs(min(0.0, pnl))
    sharpe_like = (pnl / n) / max(1e-6, (downside / n) ** 0.5) if downside else (pnl / n)
    return {
        "configuration_id": r["configuration_id"],
        "policy_version": r["policy_version"],
        "roi": vm.get("roi"),
        "gross_return": vm.get("gross_return"),
        "net_return": vm.get("net_return"),
        "max_drawdown": vm.get("max_drawdown"),
        "average_exposure_per_day": vm.get("average_exposure"),
        "active_day_ratio": vm.get("active_day_ratio"),
        "zero_capital_day_ratio": vm.get("zero_capital_day_ratio"),
        "win_frequency": vm.get("win_frequency"),
        "coupon_survival": vm.get("win_frequency"),
        "complete_coupon_failure": round(1.0 - float(vm.get("win_frequency") or 0), 8),
        "capital_efficiency": vm.get("roi"),
        "downside_deviation": round(downside / n, 6),
        "sharpe_like_score": round(sharpe_like, 6),
        "selected_day_count": vm.get("n_active_days"),
        "average_number_of_fixtures_funded": vm.get("avg_fixtures_funded"),
        "maximum_daily_loss": vm.get("max_daily_loss"),
        "validation_rank_score": r.get("validation_rank_score"),
        "threshold_values": json.dumps(r.get("threshold_values"), sort_keys=True),
    }


def _write_grid_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def _pareto_highlights(
    frontier: list[dict[str, Any]],
    grid: list[dict[str, Any]],
    *,
    baseline_id: str,
    locked_id: str,
    always_metrics: dict[str, Any],
) -> dict[str, Any]:
    by_id = {r["configuration_id"]: r for r in grid}
    max_roi = max(frontier, key=lambda x: float(x.get("roi") or -9e9), default=None)
    min_dd = min(frontier, key=lambda x: float(x.get("max_drawdown") or 9e9), default=None)
    max_eff = max(frontier, key=lambda x: float(x.get("capital_efficiency") or -9e9), default=None)

    def _balanced(pts: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not pts:
            return None
        return max(
            pts,
            key=lambda x: float(x.get("roi") or 0)
            - 0.05 * float(x.get("max_drawdown") or 0)
            - 0.02 * float(x.get("average_exposure") or 0),
        )

    return {
        "current_baseline": by_id.get(baseline_id, {}).get("policy_version") or BASELINE_POLICY["policy_version"],
        "always_bet": {
            "roi": always_metrics.get("roi"),
            "max_drawdown": always_metrics.get("max_drawdown"),
            "average_exposure": always_metrics.get("average_exposure"),
            "active_day_ratio": always_metrics.get("active_day_ratio"),
        },
        "maximum_roi_candidate": max_roi,
        "minimum_drawdown_candidate": min_dd,
        "balanced_candidate": _balanced(frontier),
        "highest_capital_efficiency_candidate": max_eff,
        "final_locked_candidate": by_id.get(locked_id),
        "frontier_n": len(frontier),
    }


def _dashboard_md(summary: dict[str, Any]) -> str:
    g = summary.get("guardrails") or {}
    return "\n".join(
        [
            "# Owner Threshold Calibration Dashboard",
            "",
            f"- Phase: `{PHASE_NAME}`",
            f"- Status: `{summary.get('status')}`",
            f"- Recommendation: `{summary.get('recommendation')}`",
            f"- Baseline commit: `{BASELINE_COMMIT}`",
            "",
            "## ROI / Risk",
            f"- Always Bet ROI: `{summary.get('always_bet_roi')}`",
            f"- Baseline Managed ROI: `{summary.get('baseline_managed_roi')}`",
            f"- Calibrated Holdout ROI: `{summary.get('calibrated_holdout_roi')}`",
            f"- Always Bet max DD: `{summary.get('always_bet_max_drawdown')}`",
            f"- Baseline max DD: `{summary.get('baseline_max_drawdown')}`",
            f"- Calibrated max DD: `{summary.get('calibrated_max_drawdown')}`",
            "",
            "## Exposure / Activity",
            f"- Always Bet avg exposure: `{summary.get('always_bet_average_exposure')}`",
            f"- Baseline avg exposure: `{summary.get('baseline_average_exposure')}`",
            f"- Calibrated avg exposure: `{summary.get('calibrated_average_exposure')}`",
            f"- Active-day ratio (holdout): `{summary.get('final_active_day_ratio')}`",
            f"- Zero-capital-day ratio (holdout): `{summary.get('zero_capital_day_ratio')}`",
            "",
            "## WATCH split",
            f"- WATCH_POSITIVE: `{summary.get('watch_positive_count')}`",
            f"- WATCH_REJECT: `{summary.get('watch_reject_count')}`",
            f"- Locked micro-allocation: `{summary.get('locked_watch_micro_allocation_ratio')}`",
            "",
            "## Guardrails",
            f"- Passed: `{list((g.get('passed') or {}).keys())}`",
            f"- Failed: `{list((g.get('failed') or {}).keys())}`",
            "",
            "**NOT DEPLOYED**",
            "",
        ]
    )


def _dashboard_html(summary: dict[str, Any]) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Threshold Calibration</title>
<style>
body{{font-family:Georgia,serif;margin:2rem;background:#0f1419;color:#e7ecf1}}
h1{{color:#7dd3c0}} .card{{background:#1a222c;padding:1rem 1.25rem;margin:1rem 0;border-left:4px solid #7dd3c0}}
code{{color:#f0c674}} .hold{{color:#f0a070}} .go{{color:#7dd3c0}}
</style></head><body>
<h1>Portfolio Manager Threshold Calibration</h1>
<div class="card"><strong>Status:</strong> <code>{summary.get('status')}</code><br/>
<strong>Recommendation:</strong> <span class="{'go' if summary.get('recommendation')=='CALIBRATION_GO' else 'hold'}">{summary.get('recommendation')}</span><br/>
<strong>Deployment:</strong> NOT DEPLOYED</div>
<div class="card"><h2>Holdout comparison</h2>
<ul>
<li>Always Bet ROI: <code>{summary.get('always_bet_roi')}</code></li>
<li>Baseline Managed ROI: <code>{summary.get('baseline_managed_roi')}</code></li>
<li>Calibrated ROI: <code>{summary.get('calibrated_holdout_roi')}</code></li>
<li>Always Bet DD: <code>{summary.get('always_bet_max_drawdown')}</code> → Calibrated: <code>{summary.get('calibrated_max_drawdown')}</code></li>
<li>Exposure Always/Base/Cal: <code>{summary.get('always_bet_average_exposure')}</code> / <code>{summary.get('baseline_average_exposure')}</code> / <code>{summary.get('calibrated_average_exposure')}</code></li>
<li>Active-day ratio: <code>{summary.get('final_active_day_ratio')}</code></li>
</ul></div>
<div class="card"><h2>Guardrails</h2>
<pre>{json.dumps(summary.get('guardrails'), indent=2)}</pre></div>
</body></html>
"""


def _final_report(summary: dict[str, Any], semantics: dict[str, Any], grade_boundary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# BET_PORTFOLIO_MANAGER_THRESHOLD_CALIBRATION_REPORT",
            "",
            f"**Status:** `{summary.get('status')}`  ",
            f"**Recommendation:** `{summary.get('recommendation')}`  ",
            f"**Baseline commit:** `{BASELINE_COMMIT}`  ",
            "**Deployment:** NOT DEPLOYED",
            "",
            "## Baseline vs calibrated vs Always Bet (final holdout)",
            "",
            "| Metric | Always Bet | Baseline Managed | Calibrated |",
            "|---|---:|---:|---:|",
            f"| ROI | {summary.get('always_bet_roi')} | {summary.get('baseline_managed_roi')} | {summary.get('calibrated_holdout_roi')} |",
            f"| Max drawdown | {summary.get('always_bet_max_drawdown')} | {summary.get('baseline_max_drawdown')} | {summary.get('calibrated_max_drawdown')} |",
            f"| Avg exposure/day | {summary.get('always_bet_average_exposure')} | {summary.get('baseline_average_exposure')} | {summary.get('calibrated_average_exposure')} |",
            "",
            "## Action semantics",
            "",
            "```json",
            json.dumps(semantics, indent=2),
            "```",
            "",
            "## Grade compression",
            "",
            "```json",
            json.dumps(grade_boundary, indent=2),
            "```",
            "",
            "## Chronological validation",
            "",
            f"- Training: `{summary.get('training_result')}`",
            f"- Validation: `{summary.get('validation_result')}`",
            f"- Final holdout: `{summary.get('final_holdout_result')}`",
            "",
            "## Guardrails",
            "",
            f"- Passed: `{list(((summary.get('guardrails') or {}).get('passed') or {}).keys())}`",
            f"- Failed: `{list(((summary.get('guardrails') or {}).get('failed') or {}).keys())}`",
            "",
            "## WATCH split",
            "",
            f"- WATCH_POSITIVE: {summary.get('watch_positive_count')}",
            f"- WATCH_REJECT: {summary.get('watch_reject_count')}",
            f"- Locked micro-allocation: {summary.get('locked_watch_micro_allocation_ratio')}",
            "",
            "## Notes",
            "",
            "- Baseline policy remains immutable (`baseline_v1_7e77aa3`).",
            "- Candidate stored separately at `calibrated_policy_candidate.json`.",
            "- No WDE/ECSE/Coverage/Insurance/freeze changes.",
            "- No production writes. NOT DEPLOYED.",
            "",
        ]
    )


def run_threshold_calibration(
    *,
    max_historical: int = 1200,
    min_historical: int = 600,
    output_dir: Path | None = None,
    fixtures: list[dict[str, Any]] | None = None,
    max_candidates: int | None = 48,
) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(output_dir) if output_dir else Path("artifacts/bet_portfolio_manager") / f"threshold_calibration_{ts}"
    out.mkdir(parents=True, exist_ok=True)

    if fixtures is None:
        corpus = build_phase5_corpus(
            min_fixtures=min(min_historical, 1000),
            max_historical=max_historical,
            top_n=8,
        )
        fixtures = list(corpus.get("primary_fixtures") or [])[:max_historical]

    # --- Baseline full-sample audits (evaluation metrics; decisions prematch-only) ---
    baseline_days = replay_all_days(fixtures, policy=BASELINE_POLICY)
    always_full = always_bet_metrics(baseline_days)
    baseline_full = summarize_days(baseline_days)

    semantics = action_semantics_audit(baseline_days)
    gate_rows, gate_summary = gate_attribution(baseline_days)
    action_perf = action_performance_audit(baseline_days)
    watch_cf = {
        "research_only": True,
        "label": "COUNTERFACTUAL_FROM_FROZEN_OUTPUTS",
        "WATCH_NO_CAPITAL": (action_perf.get("by_action") or {}).get("WATCH_NO_CAPITAL"),
        "HARD_SKIP": (action_perf.get("by_action") or {}).get("HARD_SKIP"),
    }
    grade_perf, grade_boundary = grade_audit(baseline_days)

    _write_json(out / "action_semantics_audit.json", semantics)
    _write_md(
        out / "action_semantics_audit.md",
        "# Action Semantics Audit\n\n```json\n" + json.dumps(semantics, indent=2) + "\n```\n",
    )
    _write_json(out / "gate_attribution_by_day.json", {"research_only": True, "days": gate_rows})
    _write_json(out / "gate_attribution_summary.json", gate_summary)
    _write_json(out / "action_performance_audit.json", action_perf)
    _write_json(out / "watch_counterfactual_analysis.json", watch_cf)
    _write_json(out / "grade_performance.json", grade_perf)
    _write_json(out / "grade_boundary_audit.json", grade_boundary)

    # --- Chronological splits ---
    # Use lightweight day shells (no need to re-decide for split keys)
    day_shells = [{"date": d["date"], "fixtures": d["fixtures"]} for d in baseline_days]
    splits = chronological_splits(day_shells)
    manifest = splits["manifest"]
    leak = leakage_validation(manifest)
    # Verify date set overlap
    train_dates = {d["date"] for d in splits["train"]}
    val_dates = {d["date"] for d in splits["validation"]}
    hold_dates = {d["date"] for d in splits["holdout"]}
    leak["train_validation_overlap"] = bool(train_dates & val_dates)
    leak["validation_holdout_overlap"] = bool(val_dates & hold_dates)
    leak["train_holdout_overlap"] = bool(train_dates & hold_dates)
    leak["future_leakage"] = bool(leak["train_validation_overlap"] or leak["validation_holdout_overlap"])
    _write_json(out / "chronological_split_manifest.json", manifest)
    _write_json(out / "leakage_validation.json", leak)

    train_fx = splits["train_fixtures"]
    val_fx = splits["validation_fixtures"]
    hold_fx = splits["holdout_fixtures"]
    # Freeze league reliability from training only — no val/holdout outcome leakage into gates
    lr_train = league_reliability(train_fx)

    # --- WATCH split research (train/val only) ---
    watch_research = research_watch_split(train_fx, val_fx, base_policy=BASELINE_POLICY)
    _write_json(out / "watch_split_research.json", watch_research)
    locked_micro = float(watch_research.get("final_locked_ratio") or 0.0)

    # --- Grid search ---
    policies = generate_candidate_policies()
    # Inject locked micro into a focused subset of looser policies for fairness
    enriched = []
    for p in policies:
        enriched.append(p)
        if float(p.get("watch_micro_allocation_ratio") or 0) == 0.0 and locked_micro > 0:
            p2 = copy.deepcopy(p)
            p2["watch_micro_allocation_ratio"] = locked_micro
            p2["watch_positive_score_slack"] = 6.0
            p2["policy_version"] = str(p2["policy_version"]) + f"_mlock{locked_micro}"
            enriched.append(p2)
    # Dedup + cap — always keep baseline first, then spaced sample of remaining
    seen = set()
    capped = []
    for p in enriched:
        vid = p["policy_version"]
        if vid in seen:
            continue
        seen.add(vid)
        capped.append(p)
    if max_candidates is not None and len(capped) > max_candidates:
        step = max(1, len(capped) // max_candidates)
        sampled = [capped[0]]  # baseline
        for i, p in enumerate(capped[1:], start=1):
            if len(sampled) >= max_candidates:
                break
            if i % step == 0 or float(p.get("watch_micro_allocation_ratio") or 0) == locked_micro:
                sampled.append(p)
        capped = sampled[:max_candidates]

    grid = run_grid_on_split(train_fx, val_fx, capped, league_reliability_map=lr_train)
    # Narrow on training: keep top half by train ROI then re-rank already done on val
    grid_rows = [_grid_row(r) for r in grid]
    _write_json(
        out / "threshold_grid_results.json",
        {
            "research_only": True,
            "n_candidates": len(grid),
            "results": [{k: v for k, v in r.items() if k != "policy"} for r in grid],
        },
    )
    _write_grid_csv(out / "threshold_grid_results.csv", grid_rows)

    frontier = pareto_frontier(grid)
    # Identify baseline cfg id
    baseline_cfg = next((r["configuration_id"] for r in grid if r["policy_version"] == BASELINE_POLICY["policy_version"]), grid[0]["configuration_id"])
    # Select final candidate on validation only (top ranked)
    locked = grid[0]
    locked_policy = copy.deepcopy(locked["policy"])
    # Apply locked micro from watch research if candidate has micro path
    if float(locked_policy.get("watch_micro_allocation_ratio") or 0) > 0:
        locked_policy["watch_micro_allocation_ratio"] = locked_micro
    locked_id = locked["configuration_id"]

    pareto_pack = {
        "research_only": True,
        "frontier": frontier,
        "highlights": _pareto_highlights(
            frontier,
            grid,
            baseline_id=baseline_cfg,
            locked_id=locked_id,
            always_metrics=always_bet_metrics(replay_all_days(val_fx, policy=BASELINE_POLICY)),
        ),
    }
    _write_json(out / "pareto_frontier.json", pareto_pack)
    _write_grid_csv(out / "pareto_frontier.csv", frontier if frontier else [{"configuration_id": "none"}])

    # Walk-forward folds (record only; selection already locked from primary split)
    wf_folds = walk_forward_folds(day_shells, n_folds=3)
    wf_eval = []
    for fold in wf_folds:
        f_train = [d for d in day_shells if fold["train_dates"][0] <= d["date"] <= fold["train_dates"][1]]
        f_val = [d for d in day_shells if fold["validation_dates"][0] <= d["date"] <= fold["validation_dates"][1]]
        f_train_fx = [fx for d in f_train for fx in d["fixtures"]]
        f_val_fx = [fx for d in f_val for fx in d["fixtures"]]
        lr_fold = league_reliability(f_train_fx)
        _, tm = evaluate_policy_on_fixtures(f_train_fx, locked_policy, league_reliability_map=lr_fold)
        _, vm = evaluate_policy_on_fixtures(f_val_fx, locked_policy, league_reliability_map=lr_fold)
        wf_eval.append({"fold": fold, "train_metrics": tm, "validation_metrics": vm})
    _write_json(
        out / "walk_forward_calibration.json",
        {
            "research_only": True,
            "primary_split": manifest,
            "folds": wf_eval,
            "locked_policy_version": locked_policy.get("policy_version"),
            "note": "Final thresholds locked from primary validation; folds are diagnostic only.",
        },
    )

    # --- Final holdout evaluation (exactly once; LR frozen from train) ---
    holdout_days, holdout_m = evaluate_policy_on_fixtures(
        hold_fx, locked_policy, league_reliability_map=lr_train
    )
    holdout_always = always_bet_metrics(
        replay_all_days(hold_fx, policy=BASELINE_POLICY, league_reliability_map=lr_train)
    )
    holdout_baseline_days, holdout_baseline_m = evaluate_policy_on_fixtures(
        hold_fx, BASELINE_POLICY, league_reliability_map=lr_train
    )
    guardrails = check_guardrails(holdout_m, holdout_always)
    _write_json(
        out / "final_holdout_evaluation.json",
        {
            "research_only": True,
            "locked_once": True,
            "no_retune_after_holdout": True,
            "league_reliability_frozen_from_train": True,
            "holdout_dates": manifest.get("holdout_dates"),
            "holdout_hash": manifest.get("holdout_hash"),
            "always_bet": holdout_always,
            "baseline_managed": holdout_baseline_m,
            "calibrated": holdout_m,
            "guardrails": guardrails,
            "days": _strip_fixtures(holdout_days),
        },
    )

    # Capital allocation calibration on train+val with locked policy
    capital_cal = calibrate_capital_modes(train_fx + val_fx, policy=locked_policy)
    _write_json(out / "capital_allocation_calibration.json", capital_cal)

    # Recommendation — do not force GO; HOLD on failed targets; RESEARCH_MORE if evidence incomplete
    evidence_incomplete = bool(
        leak.get("future_leakage")
        or not hold_fx
        or int(holdout_m.get("n_days") or 0) < 10
        or (holdout_m.get("roi") is None and float(holdout_m.get("active_day_ratio") or 0) > 0)
    )
    if guardrails.get("all_passed"):
        recommendation = "CALIBRATION_GO"
        status = STATUS_COMPLETE
    elif evidence_incomplete:
        recommendation = "CALIBRATION_RESEARCH_MORE"
        status = STATUS_RESEARCH_MORE
    else:
        recommendation = "CALIBRATION_HOLD"
        status = STATUS_HOLD

    train_m = locked.get("training_metrics") or {}
    val_m = locked.get("validation_metrics") or {}

    candidate_payload = {
        "policy_version": locked_policy.get("policy_version"),
        "generated_timestamp": ts,
        "training_date_range": manifest.get("train_dates"),
        "validation_date_range": manifest.get("validation_dates"),
        "holdout_date_range": manifest.get("holdout_dates"),
        "locked_thresholds": locked_policy.get("action_thresholds"),
        "grade_boundaries": locked_policy.get("grade_thresholds"),
        "action_mapping": {
            "BET": "full capital",
            "SMALL_BET": "reduced capital",
            "WATCH_POSITIVE": "micro allocation",
            "WATCH_NO_CAPITAL": "zero capital observation",
            "HARD_SKIP": "hard rejection",
        },
        "WATCH_POSITIVE_rules": watch_research.get("WATCH_POSITIVE_rules"),
        "WATCH_REJECT_rules": watch_research.get("WATCH_REJECT_rules"),
        "capital_allocation_mode": locked_policy.get("capital_mode"),
        "maximum_exposure": (locked_policy.get("gates") or {}).get("max_day_exposure_frac"),
        "micro_allocation_ratio": locked_policy.get("watch_micro_allocation_ratio"),
        "expected_active_day_ratio": holdout_m.get("active_day_ratio"),
        "gates": locked_policy.get("gates"),
        "training_metrics": train_m,
        "validation_metrics": val_m,
        "final_holdout_metrics": holdout_m,
        "comparison_with_baseline": {
            "baseline_policy": BASELINE_POLICY["policy_version"],
            "baseline_holdout": holdout_baseline_m,
            "calibrated_holdout": holdout_m,
        },
        "comparison_with_always_bet": {
            "always_bet_holdout": holdout_always,
            "calibrated_holdout": holdout_m,
        },
        "failed_and_passed_guardrails": guardrails,
        "known_limitations": [
            "Unit-stake proxy; not live bankroll sizing.",
            "Grade compression may persist if score components rarely exceed A/S thresholds.",
            "Holdout is single chronological slice; regime shifts possible.",
            "Kelly remains research-only and disabled by default.",
        ],
        "readiness_recommendation": recommendation,
        "research_only": True,
        "baseline_unchanged": True,
        "not_deployed": True,
    }
    _write_json(out / "recommended_calibrated_policy.json", candidate_payload)

    # Store separately next to package (tracked) — do not overwrite baseline
    candidate_repo_path = Path("worldcup_predictor/research/bet_portfolio_manager/calibrated_policy_candidate.json")
    _write_json(candidate_repo_path, candidate_payload)

    # Forward shadow comparison
    fwd = compare_forward_days(
        fixtures,
        baseline_policy=BASELINE_POLICY,
        candidate_policy=locked_policy,
        db_path=out / "forward_shadow_policy_comparison.db",
        max_days=30,
    )
    _write_json(out / "forward_shadow_policy_comparison.json", fwd)
    _write_json(out / "forward_shadow_policy_schema.json", FORWARD_SCHEMA)

    summary = {
        "status": status,
        "recommendation": recommendation,
        "phase": PHASE_NAME,
        "baseline_commit": BASELINE_COMMIT,
        "n_fixtures": len(fixtures),
        "n_days": len(baseline_days),
        # Full-sample baseline reproduction (must match 7e77aa3 within tolerance)
        "always_bet_roi_full_sample": always_full.get("roi"),
        "baseline_managed_roi_full_sample": baseline_full.get("roi"),
        "always_bet_max_drawdown_full_sample": always_full.get("max_drawdown"),
        "baseline_max_drawdown_full_sample": baseline_full.get("max_drawdown"),
        "always_bet_average_exposure_full_sample": always_full.get("average_exposure"),
        "baseline_average_exposure_full_sample": baseline_full.get("average_exposure"),
        # Final holdout comparison (locked evaluation)
        "always_bet_roi": holdout_always.get("roi"),
        "baseline_managed_roi": holdout_baseline_m.get("roi"),
        "calibrated_holdout_roi": holdout_m.get("roi"),
        "always_bet_max_drawdown": holdout_always.get("max_drawdown"),
        "baseline_max_drawdown": holdout_baseline_m.get("max_drawdown"),
        "calibrated_max_drawdown": holdout_m.get("max_drawdown"),
        "always_bet_average_exposure": holdout_always.get("average_exposure"),
        "baseline_average_exposure": holdout_baseline_m.get("average_exposure"),
        "calibrated_average_exposure": holdout_m.get("average_exposure"),
        "final_active_day_ratio": holdout_m.get("active_day_ratio"),
        "zero_capital_day_ratio": holdout_m.get("zero_capital_day_ratio"),
        "watch_positive_count": watch_research.get("WATCH_POSITIVE_count"),
        "watch_reject_count": watch_research.get("WATCH_REJECT_count"),
        "locked_watch_micro_allocation_ratio": locked_policy.get("watch_micro_allocation_ratio"),
        "training_result": {
            "roi": train_m.get("roi"),
            "max_drawdown": train_m.get("max_drawdown"),
            "active_day_ratio": train_m.get("active_day_ratio"),
        },
        "validation_result": {
            "roi": val_m.get("roi"),
            "max_drawdown": val_m.get("max_drawdown"),
            "active_day_ratio": val_m.get("active_day_ratio"),
        },
        "final_holdout_result": {
            "roi": holdout_m.get("roi"),
            "max_drawdown": holdout_m.get("max_drawdown"),
            "active_day_ratio": holdout_m.get("active_day_ratio"),
        },
        "guardrails": guardrails,
        "full_sample_baseline": baseline_full,
        "full_sample_always_bet": always_full,
        "artifact_dir": str(out),
        "candidate_policy_path": str(candidate_repo_path),
        "not_deployed": True,
    }
    _write_json(out / "validation_report.json", summary)
    _write_md(out / "owner_threshold_calibration_dashboard.md", _dashboard_md(summary))
    _write_md(out / "owner_threshold_calibration_dashboard.html", _dashboard_html(summary))
    # html as html
    (out / "owner_threshold_calibration_dashboard.html").write_text(_dashboard_html(summary), encoding="utf-8")
    report = _final_report(summary, semantics, grade_boundary)
    _write_md(out / "BET_PORTFOLIO_MANAGER_THRESHOLD_CALIBRATION_REPORT.md", report)
    # Also top-level research report for owner visibility (gitignored if under artifacts only)
    Path("BET_PORTFOLIO_MANAGER_THRESHOLD_CALIBRATION_REPORT.md").write_text(report, encoding="utf-8")

    return summary
