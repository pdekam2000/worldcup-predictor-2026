"""Betting Day Similarity Engine pipeline — research-only orchestration."""

from __future__ import annotations

import copy
import csv
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from worldcup_predictor.research.betting_day_similarity.clustering import (
    choose_kmeans_k,
    describe_regime,
    fit_regimes,
)
from worldcup_predictor.research.betting_day_similarity.config import load_config
from worldcup_predictor.research.betting_day_similarity.constants import (
    BASELINE_COMMIT,
    PHASE_NAME,
    STATUS_COMPLETE,
    STATUS_HOLD,
    STATUS_RESEARCH_MORE,
)
from worldcup_predictor.research.betting_day_similarity.distance_metrics import stable_inv_cov
from worldcup_predictor.research.betting_day_similarity.evaluation import (
    analyze_day,
    check_success_criteria,
    chronological_splits,
    evaluate_policies_on_split,
    score_method_on_validation,
)
from worldcup_predictor.research.betting_day_similarity.feature_provenance import (
    build_provenance,
    feature_dictionary_markdown,
    validate_leakage,
)
from worldcup_predictor.research.betting_day_similarity.forward_shadow import (
    SCHEMA as FORWARD_SCHEMA,
    store_forward_day,
    summarize_forward,
)
from worldcup_predictor.research.betting_day_similarity.historical_dataset import build_historical_day_dataset
from worldcup_predictor.research.betting_day_similarity.nearest_neighbors import knn_indices
from worldcup_predictor.research.betting_day_similarity.preprocessing import FeatureScaler, matrix_from_days


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_csv_dict(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _days_to_feature_csv(path: Path, days: list[dict[str, Any]], feature_names: list[str]) -> None:
    rows = []
    for d in days:
        row = {"day_id": d["day_id"], "vienna_date": d["vienna_date"], "cutoff_timestamp": d["cutoff_timestamp"]}
        row.update({n: (d.get("features") or {}).get(n) for n in feature_names})
        rows.append(row)
    _write_csv_dict(path, rows)


def _days_to_label_csv(path: Path, days: list[dict[str, Any]]) -> None:
    rows = []
    for d in days:
        lab = d.get("labels") or {}
        rows.append(
            {
                "day_id": d["day_id"],
                "vienna_date": d["vienna_date"],
                "baseline_action": d.get("baseline_action"),
                "calibrated_action": d.get("calibrated_action"),
                "main_ticket_count": d.get("main_ticket_count"),
                "insurance_ticket_count": d.get("insurance_ticket_count"),
                "allocated_capital": d.get("allocated_capital"),
                **{k: lab.get(k) for k in (
                    "realized_roi",
                    "net_return",
                    "max_daily_loss",
                    "coupon_survival",
                    "complete_coupon_failure",
                    "insurance_rescue_count",
                    "drawdown_state",
                    "profitable_day",
                    "losing_day",
                    "label_hash",
                    "evaluation_only",
                )},
                "input_hash": d.get("input_hash"),
            }
        )
    _write_csv_dict(path, rows)


def _analyze_split(
    split_days: list[dict[str, Any]],
    *,
    library_days: list[dict[str, Any]],
    X_library: np.ndarray,
    scaler: FeatureScaler,
    feature_names: list[str],
    method: str,
    k: int,
    inv_cov: np.ndarray | None,
    centroids: np.ndarray,
    global_mean: np.ndarray,
    train_min: np.ndarray,
    train_max: np.ndarray,
    nn_p95: float,
    centroid_p95: float,
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    Xs = scaler.transform(matrix_from_days(split_days, feature_names))
    out = []
    for i, day in enumerate(split_days):
        out.append(
            analyze_day(
                day,
                library_days=library_days,
                X_library=X_library,
                x=Xs[i],
                feature_names=feature_names,
                method=method,
                k=k,
                inv_cov=inv_cov,
                centroids=centroids,
                global_mean=global_mean,
                train_min=train_min,
                train_max=train_max,
                nn_p95=nn_p95,
                centroid_p95=centroid_p95,
                cfg=cfg,
            )
        )
    return out


def run_betting_day_similarity_research(
    *,
    output_dir: Path | None = None,
    method: str | None = None,
    neighbors: int | None = None,
    regime_method: str | None = None,
    max_historical: int = 1200,
    seed: int = 20260731,
    config_path: str | None = None,
    fixtures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    method = method or str(cfg.get("method") or "mixed")
    neighbors = int(neighbors or cfg.get("neighbors") or 10)
    regime_method = regime_method or str(cfg.get("regime_method") or "kmeans")
    cfg = {**cfg, "regime_method": regime_method}
    seed = int(cfg.get("seed") or seed)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(output_dir) if output_dir else Path("artifacts/betting_day_similarity") / f"run_{ts}"
    out.mkdir(parents=True, exist_ok=True)

    # --- Dataset ---
    ds = build_historical_day_dataset(fixtures=fixtures, max_historical=max_historical, lookback_days=int(cfg.get("lookback_days") or 90))
    days = ds["days"]
    feature_names = ds["feature_names"]
    _write_json(out / "historical_day_manifest.json", ds["manifest"])
    _days_to_feature_csv(out / "historical_day_features.csv", days, feature_names)
    _days_to_label_csv(out / "historical_day_labels.csv", days)

    # Provenance sample (all days aggregated lightly)
    prov_all = []
    for d in days[: min(20, len(days))]:
        prov_all.extend(build_provenance(d, cutoff_timestamp=d["cutoff_timestamp"]))
    _write_json(out / "day_feature_provenance.json", {"research_only": True, "rows": prov_all, "n_sampled_days": min(20, len(days))})
    leak = validate_leakage(days)
    _write_json(out / "leakage_validation.json", leak)
    _write_text(out / "feature_dictionary.md", feature_dictionary_markdown())

    # --- Chronological splits ---
    splits = chronological_splits(days)
    train, val, hold = splits["train"], splits["validation"], splits["holdout"]
    _write_json(out / "chronological_split_manifest.json", splits["manifest"])

    # --- Method comparison on validation (train library only) ---
    methods = ["euclidean", "manhattan", "cosine", "mahalanobis", "mixed"]
    k_grid = [neighbors] if neighbors else list((cfg.get("grid") or {}).get("neighbors") or [5, 10])
    comparisons = []
    for m, k in itertools.product(methods, k_grid):
        comparisons.append(score_method_on_validation(train, val, feature_names, method=m, k=k, cfg=cfg, seed=seed))
    comparisons.sort(key=lambda r: (-float(r["validation_rank_score"]), r["method"], r["k"]))
    selected = comparisons[0]
    selected_method = str(selected["method"])
    selected_k = int(selected["k"])
    n_regimes = int(selected.get("best_k_regimes") or 4)
    _write_json(out / "similarity_method_comparison.json", {"research_only": True, "results": comparisons, "selected": selected})

    # --- Lock model on train ---
    scaler = FeatureScaler().fit(matrix_from_days(train, feature_names), feature_names)
    Xtr = scaler.transform(matrix_from_days(train, feature_names))
    inv = stable_inv_cov(Xtr) if selected_method == "mahalanobis" else None
    regimes = fit_regimes(Xtr, method=regime_method, n_clusters=n_regimes, seed=seed)
    centroids = np.asarray(regimes["centroids"])
    global_mean = Xtr.mean(axis=0)
    train_min = Xtr.min(axis=0)
    train_max = Xtr.max(axis=0)

    # NN / centroid distance percentiles on train (self-excluded approx via leave-one-ish sample)
    nn_dists = []
    cent_dists = []
    for i in range(len(Xtr)):
        lib = np.vstack([Xtr[:i], Xtr[i + 1 :]]) if len(Xtr) > 1 else Xtr
        neigh = knn_indices(Xtr[i], lib, k=1, method=selected_method, inv_cov=inv)
        nn_dists.append(neigh[0][1] if neigh else 0.0)
        rid = int(np.argmin([np.linalg.norm(Xtr[i] - c) for c in centroids]))
        cent_dists.append(float(np.linalg.norm(Xtr[i] - centroids[rid])))
    nn_p95 = float(np.percentile(nn_dists, 95)) if nn_dists else 1.0
    centroid_p95 = float(np.percentile(cent_dists, 95)) if cent_dists else 1.0

    # Regime assignments on train
    assignments = []
    profiles = []
    for i, lab in enumerate(regimes["labels"]):
        assignments.append({"vienna_date": train[i]["vienna_date"], "regime_id": int(lab)})
    for rid in range(n_regimes):
        profiles.append(
            {
                "regime_id": rid,
                "size": int(sum(1 for a in assignments if a["regime_id"] == rid)),
                **describe_regime(feature_names, centroids[rid], global_mean),
            }
        )
    _write_json(out / "regime_assignments.json", {"research_only": True, "assignments": assignments})
    _write_json(out / "regime_profiles.json", {"research_only": True, "profiles": profiles})
    k_info = choose_kmeans_k(Xtr, list(cfg.get("n_regimes_candidates") or [3, 4, 5, 6]), seed=seed)
    _write_json(
        out / "regime_stability_report.json",
        {
            "research_only": True,
            "method": regime_method,
            "selected_n_regimes": n_regimes,
            "silhouette_search": k_info,
            "note": "Clusters fit on training only; holdout assigned by nearest centroid.",
        },
    )

    # --- Threshold grid on validation ---
    grid_cfg = cfg.get("grid") or {}
    grid_rows = []
    overlay_base = dict(cfg.get("overlay") or {})
    for k, fav, host, mult, micro in itertools.product(
        list(grid_cfg.get("neighbors") or [selected_k])[:3],
        list(grid_cfg.get("favorable_threshold") or [0.15])[:2],
        list(grid_cfg.get("hostile_threshold") or [-0.05])[:2],
        list(grid_cfg.get("capital_multipliers") or [1.0, 1.15])[:3],
        list(grid_cfg.get("watch_micro") or [0.10])[:2],
    ):
        # Temporarily adjust cfg recommendation thresholds via overlay multipliers
        oc = copy.deepcopy(overlay_base)
        oc["supports_capital_multiplier"] = float(mult)
        oc["watch_micro_allocation"] = float(micro)
        oc["reduce_capital_multiplier"] = 0.55
        local_cfg = {**cfg, "min_analog_count": int((grid_cfg.get("min_analog_count") or [5])[0]), "favorable_analog_roi_min": fav, "hostile_analog_roi_max": host}
        analyses_val = _analyze_split(
            val,
            library_days=train,
            X_library=Xtr,
            scaler=scaler,
            feature_names=feature_names,
            method=selected_method,
            k=int(k),
            inv_cov=inv,
            centroids=centroids,
            global_mean=global_mean,
            train_min=train_min,
            train_max=train_max,
            nn_p95=nn_p95,
            centroid_p95=centroid_p95,
            cfg=local_cfg,
        )
        # Patch recommendations using fav/host thresholds for grid
        for an in analyses_val:
            rois = [
                a["historical_roi_evaluation_only"]
                for a in an.get("analogs") or []
                if a.get("historical_roi_evaluation_only") is not None
            ]
            mean_roi = float(np.mean(rois)) if rois else None
            sim = an.get("similarity") or {}
            if an.get("ood", {}).get("ood_level") == "strongly_out_of_distribution":
                sim["recommendation"] = "OUT_OF_DISTRIBUTION"
            elif mean_roi is not None and mean_roi >= fav:
                sim["recommendation"] = "FAVORABLE_SIMILARITY"
            elif mean_roi is not None and mean_roi <= host:
                sim["recommendation"] = "HOSTILE_SIMILARITY"
            an["similarity"] = sim
        cmp_val = evaluate_policies_on_split(val, analyses_val, overlay_cfg=oc)
        ov = cmp_val["baseline_plus_similarity_overlay"]
        grid_rows.append(
            {
                "k": k,
                "favorable_threshold": fav,
                "hostile_threshold": host,
                "capital_multiplier": mult,
                "watch_micro": micro,
                "roi": ov.get("roi"),
                "max_drawdown": ov.get("max_drawdown"),
                "average_exposure": ov.get("average_exposure"),
                "active_day_ratio": ov.get("active_day_ratio"),
                "capital_efficiency": ov.get("roi"),
            }
        )
    grid_rows.sort(
        key=lambda r: (
            -(float(r["roi"]) if r["roi"] is not None else -9.0),
            float(r["max_drawdown"] or 9e9),
        )
    )
    locked_overlay = copy.deepcopy(overlay_base)
    if grid_rows:
        best = grid_rows[0]
        locked_overlay["supports_capital_multiplier"] = float(best["capital_multiplier"])
        locked_overlay["watch_micro_allocation"] = float(best["watch_micro"])
        selected_k = int(best["k"])
    _write_csv_dict(out / "similarity_threshold_grid.csv", grid_rows)
    _write_json(out / "similarity_threshold_grid.json", {"research_only": True, "results": grid_rows, "locked_overlay": locked_overlay})

    # Pareto on grid
    frontier = []
    for p in grid_rows:
        dominated = False
        for q in grid_rows:
            if q is p:
                continue
            if (
                (q.get("roi") or -9) >= (p.get("roi") or -9)
                and (q.get("max_drawdown") or 9e9) <= (p.get("max_drawdown") or 9e9)
                and (q.get("average_exposure") or 9e9) <= (p.get("average_exposure") or 9e9)
            ) and (
                (q.get("roi") or -9) > (p.get("roi") or -9)
                or (q.get("max_drawdown") or 9e9) < (p.get("max_drawdown") or 9e9)
                or (q.get("average_exposure") or 9e9) < (p.get("average_exposure") or 9e9)
            ):
                dominated = True
                break
        if not dominated:
            frontier.append(p)
    _write_json(out / "similarity_pareto_frontier.json", {"research_only": True, "frontier": frontier})

    # --- Walk-forward diagnostic ---
    wf = []
    n = len(days)
    if n >= 40:
        block = max(5, n // 5)
        for i in range(3):
            te = block * (i + 2)
            ve = min(n, te + block)
            if te >= n:
                break
            tr, va = days[:te], days[te:ve]
            if not va:
                break
            sc = score_method_on_validation(tr, va, feature_names, method=selected_method, k=selected_k, cfg=cfg, seed=seed)
            wf.append({"fold": i, "train_n": len(tr), "val_n": len(va), "score": sc})
    _write_json(out / "walk_forward_similarity_validation.json", {"research_only": True, "folds": wf, "locked_before_holdout": True})

    # --- Final holdout once ---
    analyses_hold = _analyze_split(
        hold,
        library_days=train,
        X_library=Xtr,
        scaler=scaler,
        feature_names=feature_names,
        method=selected_method,
        k=selected_k,
        inv_cov=inv,
        centroids=centroids,
        global_mean=global_mean,
        train_min=train_min,
        train_max=train_max,
        nn_p95=nn_p95,
        centroid_p95=centroid_p95,
        cfg=cfg,
    )
    hold_cmp = evaluate_policies_on_split(hold, analyses_hold, overlay_cfg=locked_overlay)
    success = check_success_criteria(hold_cmp)
    # Strip bulky fixtures from exported holdout rows
    hold_export = {k: v for k, v in hold_cmp.items() if k != "rows"}
    hold_export["locked_once"] = True
    hold_export["no_retune_after_holdout"] = True
    hold_export["selected_method"] = selected_method
    hold_export["selected_k"] = selected_k
    hold_export["success_criteria"] = success
    hold_export["ood_day_count"] = sum(
        1 for a in analyses_hold if (a.get("ood") or {}).get("ood_level") != "in_distribution"
    )
    _write_json(out / "final_holdout_similarity_evaluation.json", hold_export)

    # Policy comparison artifact
    _write_json(
        out / "policy_comparison.json",
        {
            "research_only": True,
            "holdout": hold_export,
            "baseline_pm_unchanged": True,
            "calibrated_candidate_unchanged": True,
        },
    )

    # Forward shadow (last 30 holdout/train days as research proxy)
    db_path = out / "betting_day_similarity_forward_shadow.db"
    shadow_days = (train + val + hold)[-30:]
    analyses_shadow = _analyze_split(
        shadow_days,
        library_days=train,
        X_library=Xtr,
        scaler=scaler,
        feature_names=feature_names,
        method=selected_method,
        k=selected_k,
        inv_cov=inv,
        centroids=centroids,
        global_mean=global_mean,
        train_min=train_min,
        train_max=train_max,
        nn_p95=nn_p95,
        centroid_p95=centroid_p95,
        cfg=cfg,
    )
    cum_dd = 0.0
    peak = 0.0
    eq = 0.0
    daily_reports = []
    for day, an in zip(shadow_days, analyses_shadow):
        ov = hold_cmp  # structure only
        from worldcup_predictor.research.betting_day_similarity.overlay_policy import apply_similarity_overlay

        overlay = apply_similarity_overlay(
            base_action=str(day.get("baseline_action") or "WATCH_NO_CAPITAL"),
            base_exposure=float(day.get("baseline_exposure") or 0),
            base_selected_fixture_ids=list(day.get("baseline_selected_fixture_ids") or []),
            similarity_recommendation=str((an.get("similarity") or {}).get("recommendation")),
            ood_level=str((an.get("ood") or {}).get("ood_level")),
            overlay_cfg=locked_overlay,
        )
        lab = day.get("labels") or {}
        pnl = float(lab.get("net_return") or 0)
        eq += pnl
        peak = max(peak, eq)
        cum_dd = max(cum_dd, peak - eq)
        row = {
            "vienna_date": day.get("vienna_date"),
            "feature_vector": day.get("features"),
            "similarity_score": (an.get("similarity") or {}).get("day_similarity_quality_score"),
            "nearest_analogs": an.get("analogs"),
            "regime": an.get("regime_id"),
            "ood_status": (an.get("ood") or {}).get("ood_level"),
            "baseline_action": day.get("baseline_action"),
            "calibrated_action": day.get("calibrated_action"),
            "overlay_action": overlay.get("overlay_action"),
            "capital_multiplier": overlay.get("capital_multiplier"),
            "realized_roi": lab.get("realized_roi"),
            "coupon_survival": lab.get("coupon_survival"),
            "insurance_rescue": lab.get("insurance_rescue_count"),
            "cumulative_drawdown": cum_dd,
        }
        store_forward_day(db_path, row)
        daily_reports.append(row)
    fwd_sum = summarize_forward(db_path)
    _write_json(out / "forward_shadow_summary.json", fwd_sum)
    _write_json(out / "forward_shadow_daily_report.json", {"research_only": True, "days": daily_reports, "schema": FORWARD_SCHEMA})

    # Recommendation
    if not leak.get("passed"):
        recommendation = "CALIBRATION_RESEARCH_MORE"
        status = STATUS_RESEARCH_MORE
    elif success.get("any_success"):
        recommendation = "SIMILARITY_OVERLAY_GO_RESEARCH"
        status = STATUS_COMPLETE
    else:
        recommendation = "SIMILARITY_OVERLAY_HOLD"
        status = STATUS_HOLD

    always = hold_cmp["always_bet"]
    base = hold_cmp["baseline_portfolio"]
    cal = hold_cmp["calibrated_candidate"]
    overlay_m = hold_cmp["baseline_plus_similarity_overlay"]

    summary = {
        "status": status,
        "recommendation": recommendation,
        "phase": PHASE_NAME,
        "baseline_commit": BASELINE_COMMIT,
        "historical_betting_day_count": len(days),
        "feature_count": len(feature_names),
        "selected_similarity_method": selected_method,
        "selected_k": selected_k,
        "regime_count": n_regimes,
        "ood_day_count": hold_export["ood_day_count"],
        "always_bet_roi": always.get("roi"),
        "baseline_portfolio_roi": base.get("roi"),
        "calibrated_candidate_roi": cal.get("roi"),
        "similarity_overlay_roi": overlay_m.get("roi"),
        "always_bet_max_drawdown": always.get("max_drawdown"),
        "baseline_max_drawdown": base.get("max_drawdown"),
        "similarity_overlay_max_drawdown": overlay_m.get("max_drawdown"),
        "average_exposure": {
            "always": always.get("average_exposure"),
            "baseline": base.get("average_exposure"),
            "overlay": overlay_m.get("average_exposure"),
        },
        "active_day_ratio": {
            "always": always.get("active_day_ratio"),
            "baseline": base.get("active_day_ratio"),
            "overlay": overlay_m.get("active_day_ratio"),
        },
        "final_holdout_result": hold_export,
        "guardrails_passed": list((success.get("passed") or {}).keys()),
        "guardrails_failed": list((success.get("failed") or {}).keys()),
        "success_criteria": success,
        "artifact_dir": str(out),
        "not_deployed": True,
        "baseline_pm_unchanged": True,
        "calibrated_candidate_unchanged": True,
    }
    _write_json(out / "validation_report.json", summary)

    # Dashboards / report
    md = _dashboard_md(summary, analyses_hold[:1] if analyses_hold else [])
    _write_text(out / "owner_betting_day_similarity_dashboard.md", md)
    _write_text(out / "owner_betting_day_similarity_dashboard.html", _dashboard_html(summary))
    report = _final_report(summary, leak, profiles)
    _write_text(out / "BETTING_DAY_SIMILARITY_ENGINE_REPORT.md", report)
    Path("BETTING_DAY_SIMILARITY_ENGINE_REPORT.md").write_text(report, encoding="utf-8")
    return summary


def _dashboard_md(summary: dict[str, Any], sample_analyses: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "# Owner Betting Day Similarity Dashboard",
            "",
            f"- Status: `{summary.get('status')}`",
            f"- Recommendation: `{summary.get('recommendation')}`",
            f"- Method: `{summary.get('selected_similarity_method')}` K={summary.get('selected_k')}",
            f"- Regimes: `{summary.get('regime_count')}`",
            f"- OOD days (holdout): `{summary.get('ood_day_count')}`",
            "",
            "## Holdout ROI",
            f"- Always Bet: `{summary.get('always_bet_roi')}`",
            f"- Baseline PM: `{summary.get('baseline_portfolio_roi')}`",
            f"- Calibrated: `{summary.get('calibrated_candidate_roi')}`",
            f"- Similarity Overlay: `{summary.get('similarity_overlay_roi')}`",
            "",
            "## Drawdown",
            f"- Always: `{summary.get('always_bet_max_drawdown')}`",
            f"- Baseline: `{summary.get('baseline_max_drawdown')}`",
            f"- Overlay: `{summary.get('similarity_overlay_max_drawdown')}`",
            "",
            "**NOT DEPLOYED**",
            "",
        ]
    )


def _dashboard_html(summary: dict[str, Any]) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>Betting Day Similarity</title>
<style>body{{font-family:Georgia,serif;background:#101820;color:#e8eef4;margin:2rem}}
h1{{color:#7dd3c0}}.card{{background:#1b2630;padding:1rem;margin:1rem 0;border-left:4px solid #7dd3c0}}
code{{color:#f0c674}}</style></head><body>
<h1>Betting Day Similarity Engine</h1>
<div class="card"><strong>Status:</strong> <code>{summary.get('status')}</code><br/>
<strong>Recommendation:</strong> <code>{summary.get('recommendation')}</code><br/>
<strong>Deployment:</strong> NOT DEPLOYED</div>
<div class="card"><h2>Holdout</h2>
<ul>
<li>Always ROI: <code>{summary.get('always_bet_roi')}</code></li>
<li>Baseline ROI: <code>{summary.get('baseline_portfolio_roi')}</code></li>
<li>Overlay ROI: <code>{summary.get('similarity_overlay_roi')}</code></li>
<li>Always DD: <code>{summary.get('always_bet_max_drawdown')}</code> → Overlay DD: <code>{summary.get('similarity_overlay_max_drawdown')}</code></li>
</ul></div>
</body></html>
"""


def _final_report(summary: dict[str, Any], leak: dict[str, Any], profiles: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "# BETTING_DAY_SIMILARITY_ENGINE_REPORT",
            "",
            f"**Status:** `{summary.get('status')}`  ",
            f"**Recommendation:** `{summary.get('recommendation')}`  ",
            f"**Baseline commit:** `{BASELINE_COMMIT}`  ",
            "**Deployment:** NOT DEPLOYED",
            "",
            "## Pipeline position",
            "",
            "Coverage → Insurance → **Betting Day Similarity Engine** → Portfolio Manager → Tickets → Forward Shadow",
            "",
            "## Holdout policy comparison",
            "",
            f"- Always Bet ROI: `{summary.get('always_bet_roi')}`",
            f"- Baseline Portfolio ROI: `{summary.get('baseline_portfolio_roi')}`",
            f"- Calibrated candidate ROI: `{summary.get('calibrated_candidate_roi')}`",
            f"- Similarity overlay ROI: `{summary.get('similarity_overlay_roi')}`",
            f"- Always Bet max DD: `{summary.get('always_bet_max_drawdown')}`",
            f"- Baseline max DD: `{summary.get('baseline_max_drawdown')}`",
            f"- Overlay max DD: `{summary.get('similarity_overlay_max_drawdown')}`",
            "",
            "## Similarity lock",
            "",
            f"- Method: `{summary.get('selected_similarity_method')}`",
            f"- K: `{summary.get('selected_k')}`",
            f"- Regimes: `{summary.get('regime_count')}`",
            f"- OOD days: `{summary.get('ood_day_count')}`",
            f"- Features: `{summary.get('feature_count')}`",
            f"- Historical days: `{summary.get('historical_betting_day_count')}`",
            "",
            "## Leakage validation",
            "",
            f"- Passed: `{leak.get('passed')}`",
            "",
            "## Regime profiles (training)",
            "",
            "```json",
            json.dumps(profiles, indent=2),
            "```",
            "",
            "## Guardrails",
            "",
            f"- Passed: `{summary.get('guardrails_passed')}`",
            f"- Failed: `{summary.get('guardrails_failed')}`",
            "",
            "## Limitations",
            "",
            "- Day features use research proxies where country/draw-odds/freshness are incomplete.",
            "- Similarity does not predict match results.",
            "- Overlay cannot change football predictions, markets, or freezes.",
            "- Baseline PM and calibrated candidate remain immutable.",
            "",
            "**NOT DEPLOYED**",
            "",
        ]
    )
