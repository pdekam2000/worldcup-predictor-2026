"""OOD Verifier Counterfactual Research pipeline — read-only."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from worldcup_predictor.research.betting_day_similarity.config import load_config
from worldcup_predictor.research.betting_day_similarity.evaluation import (
    chronological_splits,
    evaluate_policies_on_split,
)
from worldcup_predictor.research.betting_day_similarity.feature_stability.pipeline import (
    _analyze_hold,
    _fit_locked,
)
from worldcup_predictor.research.betting_day_similarity.historical_dataset import build_historical_day_dataset
from worldcup_predictor.research.betting_day_similarity.ood_counterfactual import (
    BASELINE_COMMIT,
    DECISION_ARCHIVE,
    DECISION_BUILD,
    LOCKED_K,
    LOCKED_METHOD,
    LOCKED_REGIMES,
    PHASE_NAME,
    STATUS_COMPLETE,
)
from worldcup_predictor.research.betting_day_similarity.ood_counterfactual.metrics import (
    delta_table,
    fixture_outcome_counts,
    summarize_policy_rows,
)
from worldcup_predictor.research.betting_day_similarity.overlay_policy import apply_similarity_overlay
from worldcup_predictor.research.betting_day_similarity.preprocessing import matrix_from_days


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _enrich_rows_with_labels(hold: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date = {d["vienna_date"]: d for d in hold}
    out = []
    for r in rows:
        day = by_date.get(r["vienna_date"]) or {}
        lab = day.get("labels") or {}
        nr = dict(r)
        nr["coupon_survival"] = lab.get("coupon_survival")
        nr["complete_coupon_failure"] = lab.get("complete_coupon_failure")
        nr["insurance_rescue_count"] = lab.get("insurance_rescue_count")
        out.append(nr)
    return out


def _classify_ood_days(
    hold: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    feature_names: list[str],
    train_mean: np.ndarray,
    train_std: np.ndarray,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (false_ood, true_ood, all_ood) inventories."""
    by_row = {r["vienna_date"]: r for r in rows}
    false_ood: list[dict[str, Any]] = []
    true_ood: list[dict[str, Any]] = []
    all_ood: list[dict[str, Any]] = []
    for day, an in zip(hold, analyses):
        ood = an.get("ood") or {}
        level = ood.get("ood_level") or "in_distribution"
        if level == "in_distribution":
            continue
        prow = by_row.get(day["vienna_date"]) or {}
        base_pnl = float(prow.get("baseline_pnl") or 0)
        feats = day.get("features") or {}
        triggers = []
        for j, name in enumerate(feature_names):
            v = feats.get(name)
            if v is None:
                continue
            std = float(train_std[j]) if float(train_std[j]) > 1e-9 else 1.0
            z = abs((float(v) - float(train_mean[j])) / std)
            if z >= 2.0:
                triggers.append({"feature": name, "z": round(z, 4)})
        triggers.sort(key=lambda x: -x["z"])
        counts = fixture_outcome_counts(day, list(day.get("baseline_selected_fixture_ids") or []))
        lab = day.get("labels") or {}
        item = {
            "date": day.get("vienna_date"),
            "day_id": day.get("day_id"),
            "ood_level": level,
            "reason_ood_fired": ood.get("reasons"),
            "triggered_features": triggers[:12],
            "similarity_score": (an.get("similarity") or {}).get("day_similarity_quality_score"),
            "distance": an.get("nn_distance") or ood.get("nn_distance"),
            "centroid_distance": ood.get("centroid_distance"),
            "regime": an.get("regime_id"),
            "portfolio_action": day.get("baseline_action"),
            "overlay_action": prow.get("overlay_action"),
            "overlay_day_action": prow.get("overlay_day_action"),
            "capital": day.get("baseline_exposure"),
            "overlay_capital": prow.get("overlay_exposure"),
            "actual_realized_roi": (lab.get("realized_roi") if lab.get("realized_roi") is not None else (
                (base_pnl / float(day.get("baseline_exposure") or 0)) if float(day.get("baseline_exposure") or 0) > 0 else None
            )),
            "baseline_pnl": base_pnl,
            "overlay_pnl": float(prow.get("overlay_pnl") or 0),
            "drawdown_state": lab.get("drawdown_state"),
            "coupon_survival": lab.get("coupon_survival"),
            "insurance_rescue": lab.get("insurance_rescue_count"),
            "number_of_profitable_fixtures": counts["profitable_fixtures"],
            "number_of_losing_fixtures": counts["losing_fixtures"],
            # Matches forensic: False OOD = OOD and baseline not losing (PnL >= 0)
            "is_false_ood": base_pnl >= 0,
            "is_true_ood": base_pnl < 0,
        }
        all_ood.append(item)
        if base_pnl < 0:
            true_ood.append(item)
        else:
            false_ood.append(item)
    return false_ood, true_ood, all_ood


def _apply_counterfactual_overlay(
    hold: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
    *,
    restore_dates: set[str],
    keep_skip_dates: set[str],
    overlay_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Replay overlay day-by-day.
    - restore_dates: force in_distribution (False OOD corrected → normal processing)
    - keep_skip_dates: force strong OOD skip (True OOD kept removed)
    Everything else identical to original analysis/recommendation.
    """
    rows = []
    for day, an in zip(hold, analyses):
        date = str(day.get("vienna_date"))
        ood_level = str((an.get("ood") or {}).get("ood_level") or "in_distribution")
        rec = str((an.get("similarity") or {}).get("recommendation") or "NEUTRAL")
        if date in restore_dates:
            ood_level = "in_distribution"
            if rec == "OUT_OF_DISTRIBUTION":
                rec = "NEUTRAL"
        if date in keep_skip_dates:
            ood_level = "strongly_out_of_distribution"
            rec = "OUT_OF_DISTRIBUTION"

        # Original baseline path metrics (unchanged)
        b_sel = list(day.get("baseline_selected_fixture_ids") or [])
        b_exp = float(day.get("baseline_exposure") or 0)

        ov = apply_similarity_overlay(
            base_action=str(day.get("baseline_action") or "WATCH_NO_CAPITAL"),
            base_exposure=b_exp,
            base_selected_fixture_ids=b_sel,
            similarity_recommendation=rec,
            ood_level=ood_level,
            overlay_cfg=overlay_cfg,
        )
        # PnL from overlay selection/scale
        from worldcup_predictor.research.betting_day_similarity.evaluation import _unit_pnl_for_selection

        o_sel = list(ov.get("selected_fixture_ids") or [])
        o_exp = float(ov.get("exposure_units") or 0)
        o_scale = (o_exp / len(o_sel)) if o_sel and o_exp > 0 else 0.0
        o_pnl = _unit_pnl_for_selection(day, o_sel, o_scale) if o_sel and o_scale > 0 else 0.0

        # Always / baseline pnl identical
        from worldcup_predictor.research.betting_day_similarity.evaluation import always_bet_day

        a_exp, a_pnl = always_bet_day(day)
        b_scale = (b_exp / len(b_sel)) if b_sel and b_exp > 0 else 0.0
        b_pnl = _unit_pnl_for_selection(day, b_sel, b_scale) if b_sel and b_scale > 0 else 0.0

        lab = day.get("labels") or {}
        rows.append(
            {
                "vienna_date": date,
                "always_exposure": a_exp,
                "always_pnl": a_pnl,
                "baseline_exposure": b_exp,
                "baseline_pnl": b_pnl,
                "overlay_exposure": o_exp,
                "overlay_pnl": o_pnl,
                "overlay_action": ov.get("overlay_action"),
                "overlay_day_action": ov.get("action"),
                "ood_level_applied": ood_level,
                "recommendation_applied": rec,
                "restored_false_ood": date in restore_dates,
                "forced_true_ood_skip": date in keep_skip_dates,
                "coupon_survival": lab.get("coupon_survival"),
                "complete_coupon_failure": lab.get("complete_coupon_failure"),
                "insurance_rescue_count": lab.get("insurance_rescue_count"),
            }
        )
    return rows


def run_ood_counterfactual_research(
    *,
    output_dir: Path | None = None,
    max_historical: int = 1200,
    fixtures: list[dict[str, Any]] | None = None,
    seed: int = 20260731,
) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(output_dir) if output_dir else Path("artifacts/betting_day_similarity") / f"ood_counterfactual_{ts}"
    out.mkdir(parents=True, exist_ok=True)

    cfg = load_config()
    overlay_cfg = dict(cfg.get("overlay") or {})

    ds = build_historical_day_dataset(fixtures=fixtures, max_historical=max_historical)
    days = ds["days"]
    feature_names = ds["feature_names"]
    splits = chronological_splits(days)
    train, hold = splits["train"], splits["holdout"]

    locked = _fit_locked(train, feature_names, method=LOCKED_METHOD, k_regimes=LOCKED_REGIMES, seed=seed)
    analyses = _analyze_hold(hold, train, feature_names, locked, cfg, method=LOCKED_METHOD, k=LOCKED_K)
    original_cmp = evaluate_policies_on_split(hold, analyses, overlay_cfg=overlay_cfg)
    original_rows = _enrich_rows_with_labels(hold, original_cmp.get("rows") or [])

    raw = matrix_from_days(train, feature_names)
    train_mean = np.nanmean(raw, axis=0)
    train_std = np.nanstd(raw, axis=0)
    train_std = np.where(train_std < 1e-9, 1.0, train_std)

    false_ood, true_ood, all_ood = _classify_ood_days(
        hold,
        analyses,
        original_rows,
        feature_names=feature_names,
        train_mean=train_mean,
        train_std=train_std,
    )
    _write_json(
        out / "false_ood_inventory.json",
        {
            "research_only": True,
            "n_false_ood": len(false_ood),
            "n_true_ood": len(true_ood),
            "n_all_ood": len(all_ood),
            "days": false_ood,
            "definition": (
                "False OOD = detector flagged OOD AND baseline Portfolio day PnL >= 0 "
                "(evaluation-only; aligned with feature-stability forensic)."
            ),
        },
    )

    false_dates = {str(d["date"]) for d in false_ood}
    true_dates = {str(d["date"]) for d in true_ood}

    # Part 2: counterfactual — restore all False OOD to normal processing
    cf_rows = _apply_counterfactual_overlay(
        hold,
        analyses,
        restore_dates=false_dates,
        keep_skip_dates=set(),  # do not force true OOD; only change False OOD
        overlay_cfg=overlay_cfg,
    )
    # For non-restored days, keep original overlay outcomes exactly
    orig_by = {r["vienna_date"]: r for r in original_rows}
    merged_cf = []
    for r in cf_rows:
        if r["vienna_date"] in false_dates:
            merged_cf.append(r)
        else:
            o = orig_by[r["vienna_date"]]
            merged_cf.append(
                {
                    **r,
                    "overlay_exposure": o.get("overlay_exposure"),
                    "overlay_pnl": o.get("overlay_pnl"),
                    "overlay_action": o.get("overlay_action"),
                    "overlay_day_action": o.get("overlay_day_action"),
                }
            )

    original_overlay = summarize_policy_rows(original_rows, "overlay_exposure", "overlay_pnl")
    original_baseline = summarize_policy_rows(original_rows, "baseline_exposure", "baseline_pnl")
    original_always = summarize_policy_rows(original_rows, "always_exposure", "always_pnl")
    cf_overlay = summarize_policy_rows(merged_cf, "overlay_exposure", "overlay_pnl")
    deltas = delta_table(original_overlay, cf_overlay)

    _write_json(
        out / "counterfactual_false_ood_replay.json",
        {
            "research_only": True,
            "change": "False OOD → normal processing only",
            "unchanged": [
                "football_predictions",
                "coverage",
                "insurance",
                "portfolio_manager",
                "similarity_engine",
                "ood_detector_thresholds",
            ],
            "n_days_restored": len(false_dates),
            "original_overlay": original_overlay,
            "counterfactual_overlay": cf_overlay,
            "original_baseline": original_baseline,
            "original_always": original_always,
            "delta_table": deltas,
            "days": merged_cf,
        },
    )

    # Part 4: False OOD value
    missed = []
    for d in false_ood:
        # Missed vs original overlay: baseline pnl that was zeroed by OOD skip / reduction
        date = d["date"]
        o = orig_by.get(date) or {}
        base_pnl = float(d.get("baseline_pnl") or 0)
        ov_pnl = float(o.get("overlay_pnl") or 0)
        missed_profit = max(0.0, base_pnl - ov_pnl)
        missed.append({**d, "missed_profit": round(missed_profit, 6)})
    missed.sort(key=lambda x: -float(x["missed_profit"]))
    mp_vals = [float(x["missed_profit"]) for x in missed]
    value = {
        "research_only": True,
        "n_false_ood": len(missed),
        "total_missed_profit": round(sum(mp_vals), 6),
        "average_missed_profit": round(float(np.mean(mp_vals)), 6) if mp_vals else 0.0,
        "median_missed_profit": round(float(np.median(mp_vals)), 6) if mp_vals else 0.0,
        "maximum_missed_profit": round(max(mp_vals), 6) if mp_vals else 0.0,
        "minimum_missed_profit": round(min(mp_vals), 6) if mp_vals else 0.0,
        "distribution_quartiles": {
            "q25": round(float(np.percentile(mp_vals, 25)), 6) if mp_vals else None,
            "q50": round(float(np.percentile(mp_vals, 50)), 6) if mp_vals else None,
            "q75": round(float(np.percentile(mp_vals, 75)), 6) if mp_vals else None,
        },
        "contribution_to_roi_delta": deltas.get("roi"),
        "contribution_to_drawdown_delta": deltas.get("max_drawdown"),
        "contribution_to_exposure_delta": deltas.get("average_exposure"),
        "ranked_false_ood_days": missed,
    }
    _write_json(out / "false_ood_value_analysis.json", value)

    # Part 5: recovery sensitivity 10/25/50/75/100%
    # Deterministic order: highest missed profit first
    ordered_dates = [d["date"] for d in missed]
    curve = []
    for pct in (0.10, 0.25, 0.50, 0.75, 1.00):
        n_rec = int(round(len(ordered_dates) * pct))
        restore = set(ordered_dates[:n_rec])
        rows_p = _apply_counterfactual_overlay(
            hold, analyses, restore_dates=restore, keep_skip_dates=set(), overlay_cfg=overlay_cfg
        )
        merged_p = []
        for r in rows_p:
            if r["vienna_date"] in restore:
                merged_p.append(r)
            else:
                o = orig_by[r["vienna_date"]]
                merged_p.append(
                    {
                        **r,
                        "overlay_exposure": o.get("overlay_exposure"),
                        "overlay_pnl": o.get("overlay_pnl"),
                    }
                )
        m = summarize_policy_rows(merged_p, "overlay_exposure", "overlay_pnl")
        curve.append(
            {
                "recovery_fraction": pct,
                "n_restored": n_rec,
                "roi": m.get("roi"),
                "net_profit": m.get("net_profit"),
                "max_drawdown": m.get("max_drawdown"),
                "average_exposure": m.get("average_exposure"),
                "winning_days": m.get("winning_days"),
                "losing_days": m.get("losing_days"),
            }
        )
    _write_json(
        out / "false_ood_recovery_curve.json",
        {
            "research_only": True,
            "selection_order": "highest_missed_profit_first",
            "curve": curve,
            "original_roi": original_overlay.get("roi"),
        },
    )

    # Part 6: Perfect OOD upper bound — True OOD stay skipped, all False OOD restored
    perfect_rows_raw = _apply_counterfactual_overlay(
        hold,
        analyses,
        restore_dates=false_dates,
        keep_skip_dates=true_dates,
        overlay_cfg=overlay_cfg,
    )
    # For non-OOD days use original overlay; for restored use CF; for true OOD force skip already
    perfect_merged = []
    for r in perfect_rows_raw:
        date = r["vienna_date"]
        if date in false_dates or date in true_dates:
            perfect_merged.append(r)
        else:
            o = orig_by[date]
            perfect_merged.append(
                {
                    **r,
                    "overlay_exposure": o.get("overlay_exposure"),
                    "overlay_pnl": o.get("overlay_pnl"),
                }
            )
    perfect = summarize_policy_rows(perfect_merged, "overlay_exposure", "overlay_pnl")
    _write_json(
        out / "perfect_ood_upper_bound.json",
        {
            "research_only": True,
            "definition": "Keep True OOD removed; restore all False OOD to normal processing.",
            "metrics": perfect,
            "vs_original_overlay": delta_table(original_overlay, perfect),
            "vs_baseline": delta_table(original_baseline, perfect),
            "vs_always": delta_table(original_always, perfect),
        },
    )

    # Recovered day counts
    orig_win = sum(1 for r in original_rows if float(r.get("overlay_pnl") or 0) > 0)
    cf_win = sum(1 for r in merged_cf if float(r.get("overlay_pnl") or 0) > 0)
    orig_lose = sum(1 for r in original_rows if float(r.get("overlay_pnl") or 0) < 0)
    cf_lose = sum(1 for r in merged_cf if float(r.get("overlay_pnl") or 0) < 0)
    recovered_profit = float(cf_overlay.get("net_profit") or 0) - float(original_overlay.get("net_profit") or 0)

    # Part 7–8 cost benefit + hard decision
    roi_gain = None
    if original_overlay.get("roi") is not None and cf_overlay.get("roi") is not None:
        roi_gain = float(cf_overlay["roi"]) - float(original_overlay["roi"])
    dd_change = float(cf_overlay.get("max_drawdown") or 0) - float(original_overlay.get("max_drawdown") or 0)
    exp_change = float(cf_overlay.get("average_exposure") or 0) - float(original_overlay.get("average_exposure") or 0)

    # Decision rule (quantitative, no middle):
    # BUILD if counterfactual ROI improves vs original overlay AND ROI moves toward/above baseline
    #   OR perfect upper bound ROI >= baseline ROI with DD still below Always Bet
    # else ARCHIVE
    always_dd = float(original_always.get("max_drawdown") or 9e9)
    base_roi = original_baseline.get("roi")
    cf_roi = cf_overlay.get("roi")
    perfect_roi = perfect.get("roi")
    improves = roi_gain is not None and roi_gain > 0.01
    reaches_baseline = (
        cf_roi is not None and base_roi is not None and cf_roi >= float(base_roi) - 1e-9
    )
    perfect_attractive = (
        perfect_roi is not None
        and base_roi is not None
        and float(perfect_roi) >= float(base_roi) - 0.02
        and float(perfect.get("max_drawdown") or 9e9) <= 0.85 * always_dd
        and recovered_profit > 0
    )
    build = bool((improves and (reaches_baseline or recovered_profit > 2.0)) or perfect_attractive)

    # Stronger evidence from forensic: 68 false OOD — if restoring them improves ROI materially, BUILD
    if roi_gain is not None and roi_gain > 0.03 and recovered_profit > 0:
        build = True
    if roi_gain is not None and roi_gain <= 0 and (perfect_roi is None or (base_roi is not None and perfect_roi < float(base_roi) - 0.05)):
        build = False

    decision = DECISION_BUILD if build else DECISION_ARCHIVE

    cost_benefit = {
        "research_only": True,
        "potential_roi_improvement": round(roi_gain, 8) if roi_gain is not None else None,
        "potential_drawdown_increase": round(dd_change, 8),
        "potential_exposure_increase": round(exp_change, 8),
        "recovered_profit": round(recovered_profit, 6),
        "perfect_ood_roi": perfect.get("roi"),
        "perfect_ood_drawdown": perfect.get("max_drawdown"),
        "potential_complexity": "Medium — verifier on top of existing OOD detector",
        "risk": "Medium — verifier errors could reintroduce True OOD losses",
        "maintenance_cost": "Medium — needs ongoing calibration monitoring",
        "expected_benefit": (
            "High" if build and (roi_gain or 0) > 0.05 else ("Medium" if build else "Low")
        ),
        "decision_inputs": {
            "improves": improves,
            "reaches_baseline": reaches_baseline,
            "perfect_attractive": perfect_attractive,
            "n_false_ood": len(false_ood),
            "n_true_ood": len(true_ood),
        },
    }
    _write_json(out / "cost_benefit_analysis.json", cost_benefit)

    recommendation = {
        "research_only": True,
        "not_deployed": True,
        "decision": decision,
        "rationale": (
            "Correcting False OOD improves overlay ROI/profit enough that building a verifier is justified."
            if decision == DECISION_BUILD
            else "Correcting False OOD does not produce a compelling performance ceiling; archive Similarity Engine research path."
        ),
        "evidence": {
            "original_overlay_roi": original_overlay.get("roi"),
            "counterfactual_overlay_roi": cf_overlay.get("roi"),
            "perfect_ood_roi": perfect.get("roi"),
            "baseline_roi": base_roi,
            "always_roi": original_always.get("roi"),
            "recovered_profit": round(recovered_profit, 6),
            "drawdown_original": original_overlay.get("max_drawdown"),
            "drawdown_counterfactual": cf_overlay.get("max_drawdown"),
            "drawdown_perfect": perfect.get("max_drawdown"),
            "false_ood": len(false_ood),
            "true_ood": len(true_ood),
        },
        "no_middle_ground": True,
    }
    _write_json(out / "recommendation.json", recommendation)

    summary = {
        "status": STATUS_COMPLETE,
        "phase": PHASE_NAME,
        "baseline_commit": BASELINE_COMMIT,
        "not_deployed": True,
        "similarity_unchanged": True,
        "portfolio_unchanged": True,
        "ood_detector_unchanged": True,
        "n_false_ood": len(false_ood),
        "n_true_ood": len(true_ood),
        "original_roi": original_overlay.get("roi"),
        "counterfactual_roi": cf_overlay.get("roi"),
        "perfect_ood_roi": perfect.get("roi"),
        "baseline_roi": base_roi,
        "always_roi": original_always.get("roi"),
        "original_drawdown": original_overlay.get("max_drawdown"),
        "counterfactual_drawdown": cf_overlay.get("max_drawdown"),
        "perfect_ood_drawdown": perfect.get("max_drawdown"),
        "original_exposure": original_overlay.get("average_exposure"),
        "counterfactual_exposure": cf_overlay.get("average_exposure"),
        "perfect_ood_exposure": perfect.get("average_exposure"),
        "recovered_profit": round(recovered_profit, 6),
        "recovered_winning_days_delta": cf_win - orig_win,
        "recovered_losing_days_delta": cf_lose - orig_lose,
        "decision": decision,
        "delta_table": deltas,
        "recovery_curve": curve,
        "artifact_dir": str(out),
    }
    _write_json(out / "validation_report.json", summary)

    md = _dashboard_md(summary, recommendation, value)
    _write_text(out / "owner_ood_counterfactual_dashboard.md", md)
    _write_text(out / "owner_ood_counterfactual_dashboard.html", _dashboard_html(summary, decision))
    report = _final_report(summary, recommendation, cost_benefit, value)
    _write_text(out / "OOD_VERIFIER_COUNTERFACTUAL_REPORT.md", report)
    # Root report only for full historical runs (not synthetic test corpora).
    if fixtures is None:
        Path("OOD_VERIFIER_COUNTERFACTUAL_REPORT.md").write_text(report, encoding="utf-8")
    return summary


def _dashboard_md(summary, recommendation, value) -> str:
    return "\n".join(
        [
            "# Owner OOD Counterfactual Dashboard",
            "",
            f"- Status: `{summary.get('status')}`",
            f"- Decision: `{recommendation.get('decision')}`",
            f"- False OOD: `{summary.get('n_false_ood')}` / True OOD: `{summary.get('n_true_ood')}`",
            f"- Original ROI: `{summary.get('original_roi')}`",
            f"- Counterfactual ROI: `{summary.get('counterfactual_roi')}`",
            f"- Perfect OOD ROI: `{summary.get('perfect_ood_roi')}`",
            f"- Recovered profit: `{summary.get('recovered_profit')}`",
            f"- Total missed profit (inventory): `{value.get('total_missed_profit')}`",
            "",
            "**NOT DEPLOYED**",
            "",
        ]
    )


def _dashboard_html(summary: dict[str, Any], decision: str) -> str:
    color = "#7dd3c0" if decision == DECISION_BUILD else "#f0a070"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>OOD Counterfactual</title>
<style>body{{font-family:Georgia,serif;background:#101820;color:#e8eef4;margin:2rem}}
h1{{color:{color}}}.card{{background:#1b2630;padding:1rem;margin:1rem 0;border-left:4px solid {color}}}
code{{color:#f0c674}}</style></head><body>
<h1>OOD Verifier Counterfactual</h1>
<div class="card"><strong>Decision:</strong> <code>{decision}</code><br/>
<strong>Original ROI:</strong> <code>{summary.get('original_roi')}</code><br/>
<strong>Counterfactual ROI:</strong> <code>{summary.get('counterfactual_roi')}</code><br/>
<strong>Perfect OOD ROI:</strong> <code>{summary.get('perfect_ood_roi')}</code><br/>
<strong>Recovered profit:</strong> <code>{summary.get('recovered_profit')}</code><br/>
<strong>Deployment:</strong> NOT DEPLOYED</div>
</body></html>
"""


def _final_report(summary, recommendation, cost_benefit, value) -> str:
    return "\n".join(
        [
            "# OOD_VERIFIER_COUNTERFACTUAL_REPORT",
            "",
            f"**Status:** `{summary.get('status')}`  ",
            f"**Decision:** `{recommendation.get('decision')}`  ",
            f"**Baseline commit:** `{BASELINE_COMMIT}`  ",
            "**Deployment:** NOT DEPLOYED",
            "",
            "## Question",
            "",
            "If False OOD decisions had been corrected, would the betting system actually become better?",
            "",
            f"**Answer / decision:** `{recommendation.get('decision')}`",
            "",
            f"Rationale: {recommendation.get('rationale')}",
            "",
            "## Metrics",
            "",
            f"- Original overlay ROI: `{summary.get('original_roi')}`",
            f"- Counterfactual ROI: `{summary.get('counterfactual_roi')}`",
            f"- Perfect OOD ROI: `{summary.get('perfect_ood_roi')}`",
            f"- Original DD: `{summary.get('original_drawdown')}` → CF `{summary.get('counterfactual_drawdown')}` → Perfect `{summary.get('perfect_ood_drawdown')}`",
            f"- Original exposure: `{summary.get('original_exposure')}` → CF `{summary.get('counterfactual_exposure')}`",
            f"- Recovered profit: `{summary.get('recovered_profit')}`",
            f"- False OOD missed profit total: `{value.get('total_missed_profit')}`",
            "",
            "## Cost-benefit",
            "",
            "```json",
            json.dumps(cost_benefit, indent=2),
            "```",
            "",
            "**NOT DEPLOYED** — no OOD Verifier built in this phase.",
            "",
        ]
    )
