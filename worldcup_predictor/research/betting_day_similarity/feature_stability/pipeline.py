"""Forensic audit pipeline — additive research only. No retune / no deploy."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from worldcup_predictor.research.betting_day_similarity.clustering import choose_kmeans_k, fit_regimes
from worldcup_predictor.research.betting_day_similarity.config import load_config
from worldcup_predictor.research.betting_day_similarity.distance_metrics import stable_inv_cov
from worldcup_predictor.research.betting_day_similarity.evaluation import (
    analyze_day,
    chronological_splits,
    evaluate_policies_on_split,
    score_method_on_validation,
)
from worldcup_predictor.research.betting_day_similarity.feature_stability import (
    BASELINE_COMMIT,
    LOCKED_K,
    LOCKED_METHOD,
    LOCKED_REGIMES,
    PHASE_NAME,
    STATUS_COMPLETE,
)
from worldcup_predictor.research.betting_day_similarity.feature_stability.importance_ablation import (
    discover_minimal_feature_set,
    estimate_feature_importance,
    run_feature_ablation,
)
from worldcup_predictor.research.betting_day_similarity.feature_stability.ood_forensic import ood_day_analysis
from worldcup_predictor.research.betting_day_similarity.feature_stability.root_cause import (
    component_contribution,
    failure_root_cause,
)
from worldcup_predictor.research.betting_day_similarity.feature_stability.stability_drift import (
    distribution_drift_report,
    feature_stability_stats,
)
from worldcup_predictor.research.betting_day_similarity.historical_dataset import build_historical_day_dataset
from worldcup_predictor.research.betting_day_similarity.nearest_neighbors import knn_indices
from worldcup_predictor.research.betting_day_similarity.overlay_policy import apply_similarity_overlay
from worldcup_predictor.research.betting_day_similarity.preprocessing import FeatureScaler, matrix_from_days


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fit_locked(
    train: list[dict[str, Any]],
    feature_names: list[str],
    *,
    method: str,
    k_regimes: int,
    seed: int,
) -> dict[str, Any]:
    scaler = FeatureScaler().fit(matrix_from_days(train, feature_names), feature_names)
    Xtr = scaler.transform(matrix_from_days(train, feature_names))
    inv = stable_inv_cov(Xtr) if method == "mahalanobis" else None
    regimes = fit_regimes(Xtr, method="kmeans", n_clusters=k_regimes, seed=seed)
    centroids = np.asarray(regimes["centroids"])
    nn_dists = []
    cent_dists = []
    for i in range(len(Xtr)):
        lib = np.vstack([Xtr[:i], Xtr[i + 1 :]]) if len(Xtr) > 1 else Xtr
        neigh = knn_indices(Xtr[i], lib, k=1, method=method, inv_cov=inv)
        nn_dists.append(neigh[0][1] if neigh else 0.0)
        rid = int(np.argmin([np.linalg.norm(Xtr[i] - c) for c in centroids]))
        cent_dists.append(float(np.linalg.norm(Xtr[i] - centroids[rid])))
    return {
        "scaler": scaler,
        "Xtr": Xtr,
        "inv": inv,
        "centroids": centroids,
        "global_mean": Xtr.mean(axis=0),
        "train_min": Xtr.min(axis=0),
        "train_max": Xtr.max(axis=0),
        "nn_p95": float(np.percentile(nn_dists, 95)) if nn_dists else 1.0,
        "centroid_p95": float(np.percentile(cent_dists, 95)) if cent_dists else 1.0,
        "raw_mean": np.nanmean(matrix_from_days(train, feature_names), axis=0),
        "raw_std": np.nanstd(matrix_from_days(train, feature_names), axis=0),
    }


def _analyze_hold(
    hold: list[dict[str, Any]],
    train: list[dict[str, Any]],
    feature_names: list[str],
    locked: dict[str, Any],
    cfg: dict[str, Any],
    *,
    method: str,
    k: int,
    force_ood_level: str | None = None,
    force_recommendation: str | None = None,
) -> list[dict[str, Any]]:
    Xs = locked["scaler"].transform(matrix_from_days(hold, feature_names))
    out = []
    for i, day in enumerate(hold):
        an = analyze_day(
            day,
            library_days=train,
            X_library=locked["Xtr"],
            x=Xs[i],
            feature_names=feature_names,
            method=method,
            k=k,
            inv_cov=locked["inv"],
            centroids=locked["centroids"],
            global_mean=locked["global_mean"],
            train_min=locked["train_min"],
            train_max=locked["train_max"],
            nn_p95=locked["nn_p95"],
            centroid_p95=locked["centroid_p95"],
            cfg=cfg,
        )
        if force_ood_level is not None:
            an["ood"] = {**(an.get("ood") or {}), "ood_level": force_ood_level}
        if force_recommendation is not None:
            an["similarity"] = {**(an.get("similarity") or {}), "recommendation": force_recommendation}
        out.append(an)
    return out


def run_feature_stability_forensic(
    *,
    output_dir: Path | None = None,
    max_historical: int = 1200,
    fixtures: list[dict[str, Any]] | None = None,
    seed: int = 20260731,
    max_ablation_features: int = 18,
) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(output_dir) if output_dir else Path("artifacts/betting_day_similarity") / f"feature_stability_{ts}"
    out.mkdir(parents=True, exist_ok=True)

    cfg = load_config()
    overlay_cfg = dict(cfg.get("overlay") or {})

    ds = build_historical_day_dataset(fixtures=fixtures, max_historical=max_historical)
    days = ds["days"]
    feature_names = ds["feature_names"]
    splits = chronological_splits(days)
    train, val, hold = splits["train"], splits["validation"], splits["holdout"]

    Xtr_raw = matrix_from_days(train, feature_names)
    Xva_raw = matrix_from_days(val, feature_names)
    Xho_raw = matrix_from_days(hold, feature_names)

    # Part 1–2
    stability = feature_stability_stats(Xtr_raw, Xva_raw, Xho_raw, feature_names)
    drift = distribution_drift_report(Xtr_raw, Xva_raw, Xho_raw, feature_names)
    _write_json(out / "feature_stability_report.json", stability)
    _write_json(out / "distribution_drift_report.json", drift)

    # Locked similarity replay (cosine/K=10/regimes=3) — forensic only
    method = LOCKED_METHOD
    k = LOCKED_K
    locked = _fit_locked(train, feature_names, method=method, k_regimes=LOCKED_REGIMES, seed=seed)
    analyses = _analyze_hold(hold, train, feature_names, locked, cfg, method=method, k=k)
    cmp_full = evaluate_policies_on_split(hold, analyses, overlay_cfg=overlay_cfg)
    rows = cmp_full.get("rows") or []

    # Part 3–4 OOD
    ood_rep = ood_day_analysis(
        hold,
        analyses,
        rows,
        feature_names=feature_names,
        train_mean=locked["raw_mean"],
        train_std=np.where(locked["raw_std"] < 1e-9, 1.0, locked["raw_std"]),
    )
    _write_json(out / "ood_day_analysis.json", ood_rep)

    ood_trigger_counts: dict[str, int] = {}
    for d in ood_rep.get("days") or []:
        for t in d.get("triggering_features") or []:
            ood_trigger_counts[t["feature"]] = ood_trigger_counts.get(t["feature"], 0) + 1

    # Helper: evaluate subset on holdout (ablation / minimal)
    def evaluate_subset(subset: list[str]) -> dict[str, Any]:
        loc = _fit_locked(train, subset, method=method, k_regimes=LOCKED_REGIMES, seed=seed)
        ans = _analyze_hold(hold, train, subset, loc, cfg, method=method, k=k)
        return evaluate_policies_on_split(hold, ans, overlay_cfg=overlay_cfg)

    # Part 6 ablation (bounded for runtime)
    # Prioritize ablating most unstable / drifted features
    priority = []
    seen = set()
    for name in (stability.get("top_unstable") or []) + (drift.get("top_drifted") or []) + feature_names:
        if name not in seen and name in feature_names:
            seen.add(name)
            priority.append(name)
    ablation = run_feature_ablation(
        priority,
        evaluate_subset=evaluate_subset,
        max_single_features=min(max_ablation_features, len(priority)),
    )
    # Map ablation deltas for importance
    abl_delta = {
        r["removed_feature"]: float(r.get("roi_delta_vs_full") or 0)
        for r in ablation.get("single_feature_ablation") or []
    }
    _write_json(out / "feature_ablation_report.json", ablation)

    # Part 5 importance
    importance = estimate_feature_importance(
        feature_names,
        instability_ranked=stability.get("ranked_by_instability") or [],
        drift_ranked=drift.get("ranked_by_train_holdout_drift") or [],
        ood_trigger_counts=ood_trigger_counts,
        ablation_delta_roi=abl_delta,
    )
    _write_json(out / "feature_importance.json", importance)

    # Part 7 minimal set
    minimal = discover_minimal_feature_set(
        feature_names,
        importance.get("ranked") or [],
        evaluate_subset=evaluate_subset,
        sizes=(min(72, len(feature_names)), 40, 25, 15, 10),
    )
    _write_json(out / "minimal_feature_set.json", minimal)

    # Part 8 regime stability
    sil = choose_kmeans_k(locked["Xtr"], [2, 3, 4, 5, 6], seed=seed)
    # Assign holdout regimes over time
    Xs_hold = locked["scaler"].transform(matrix_from_days(hold, feature_names))
    hold_regimes = []
    for i, day in enumerate(hold):
        rid = int(np.argmin([np.linalg.norm(Xs_hold[i] - c) for c in locked["centroids"]]))
        hold_regimes.append({"vienna_date": day["vienna_date"], "regime_id": rid})
    # Drift of regime proportions train vs hold
    tr_labs = fit_regimes(locked["Xtr"], method="kmeans", n_clusters=LOCKED_REGIMES, seed=seed)["labels"]
    train_prop = {i: tr_labs.count(i) / max(1, len(tr_labs)) for i in range(LOCKED_REGIMES)}
    hold_prop = {
        i: sum(1 for r in hold_regimes if r["regime_id"] == i) / max(1, len(hold_regimes))
        for i in range(LOCKED_REGIMES)
    }
    regime_stability = {
        "research_only": True,
        "locked_regime_count": LOCKED_REGIMES,
        "silhouette_search": sil,
        "should_there_be_more": bool(sil.get("best_k") and int(sil["best_k"]) > LOCKED_REGIMES),
        "suggested_k_by_silhouette": sil.get("best_k"),
        "train_regime_proportions": train_prop,
        "holdout_regime_proportions": hold_prop,
        "proportion_l1_drift": round(float(sum(abs(train_prop[i] - hold_prop[i]) for i in range(LOCKED_REGIMES))), 8),
        "holdout_assignments": hold_regimes,
        "regimes_appear_unstable": float(sum(abs(train_prop[i] - hold_prop[i]) for i in range(LOCKED_REGIMES))) > 0.25,
    }
    _write_json(out / "regime_stability.json", regime_stability)

    # Part 9 method forensic (no retune — compare validation ranks only)
    methods = ["euclidean", "manhattan", "cosine", "mahalanobis", "mixed"]
    method_rows = []
    for m in methods:
        sc = score_method_on_validation(train, val, feature_names, method=m, k=k, cfg=cfg, seed=seed)
        method_rows.append(sc)
    method_rows.sort(key=lambda r: -float(r["validation_rank_score"]))
    cosine_rank = next(i for i, r in enumerate(method_rows) if r["method"] == "cosine")
    method_forensic = {
        "research_only": True,
        "no_retune": True,
        "locked_method": LOCKED_METHOD,
        "locked_k": LOCKED_K,
        "validation_ranking": method_rows,
        "cosine_rank_index_0_based": cosine_rank,
        "cosine_deserved_to_win": cosine_rank == 0,
        "winner_on_validation": method_rows[0]["method"] if method_rows else None,
        "note": "Forensic comparison only; locked Similarity Overlay method unchanged.",
    }
    _write_json(out / "similarity_method_forensic.json", method_forensic)

    # Part 10 component contribution
    def evaluate_variant(name: str) -> dict[str, Any]:
        if name == "baseline_only":
            m = cmp_full["baseline_portfolio"]
            return {
                "roi": m.get("roi"),
                "max_drawdown": m.get("max_drawdown"),
                "average_exposure": m.get("average_exposure"),
                "active_day_ratio": m.get("active_day_ratio"),
            }
        if name == "full_overlay":
            m = cmp_full["baseline_plus_similarity_overlay"]
            return {
                "roi": m.get("roi"),
                "max_drawdown": m.get("max_drawdown"),
                "average_exposure": m.get("average_exposure"),
                "active_day_ratio": m.get("active_day_ratio"),
            }
        if name == "no_ood":
            ans = _analyze_hold(
                hold, train, feature_names, locked, cfg, method=method, k=k, force_ood_level="in_distribution"
            )
            # Keep recommendations but neutralize strong OOD skips
            for an in ans:
                if (an.get("similarity") or {}).get("recommendation") == "OUT_OF_DISTRIBUTION":
                    an["similarity"]["recommendation"] = "NEUTRAL"
            cmp = evaluate_policies_on_split(hold, ans, overlay_cfg=overlay_cfg)
            m = cmp["baseline_plus_similarity_overlay"]
            return {
                "roi": m.get("roi"),
                "max_drawdown": m.get("max_drawdown"),
                "average_exposure": m.get("average_exposure"),
                "active_day_ratio": m.get("active_day_ratio"),
            }
        if name == "no_regime":
            # Neutralize regime confidence effect by forcing NEUTRAL unless OOD strong
            ans = copy.deepcopy(analyses)
            for an in ans:
                if (an.get("ood") or {}).get("ood_level") != "strongly_out_of_distribution":
                    an["similarity"] = {**(an.get("similarity") or {}), "recommendation": "NEUTRAL"}
            cmp = evaluate_policies_on_split(hold, ans, overlay_cfg=overlay_cfg)
            m = cmp["baseline_plus_similarity_overlay"]
            return {
                "roi": m.get("roi"),
                "max_drawdown": m.get("max_drawdown"),
                "average_exposure": m.get("average_exposure"),
                "active_day_ratio": m.get("active_day_ratio"),
            }
        if name == "no_similarity_score":
            # Apply only OOD skips; otherwise leave baseline action (SIMILARITY_NEUTRAL)
            ans = copy.deepcopy(analyses)
            for an in ans:
                if (an.get("ood") or {}).get("ood_level") == "strongly_out_of_distribution":
                    an["similarity"] = {**(an.get("similarity") or {}), "recommendation": "OUT_OF_DISTRIBUTION"}
                else:
                    an["similarity"] = {**(an.get("similarity") or {}), "recommendation": "NEUTRAL"}
            cmp = evaluate_policies_on_split(hold, ans, overlay_cfg=overlay_cfg)
            m = cmp["baseline_plus_similarity_overlay"]
            return {
                "roi": m.get("roi"),
                "max_drawdown": m.get("max_drawdown"),
                "average_exposure": m.get("average_exposure"),
                "active_day_ratio": m.get("active_day_ratio"),
            }
        return {}

    contrib = component_contribution(evaluate_variant=evaluate_variant)
    _write_json(out / "component_contribution.json", contrib)

    # Part 11–12 root cause + recommendations
    root = failure_root_cause(
        false_ood=ood_rep,
        component=contrib,
        drift=drift,
        stability=stability,
        ablation=ablation,
        holdout_cmp=cmp_full,
    )
    _write_json(out / "failure_root_cause.json", root)

    fo = ood_rep.get("false_ood_metrics") or {}
    summary = {
        "status": STATUS_COMPLETE,
        "phase": PHASE_NAME,
        "baseline_commit": BASELINE_COMMIT,
        "research_only": True,
        "not_deployed": True,
        "similarity_overlay_unchanged": True,
        "portfolio_manager_unchanged": True,
        "historical_days": len(days),
        "feature_count": len(feature_names),
        "holdout_ood_days": ood_rep.get("n_ood_days"),
        "false_ood_count": fo.get("false_ood"),
        "true_ood_count": fo.get("true_ood"),
        "false_alarm_rate": fo.get("false_alarm_rate"),
        "ood_too_aggressive": fo.get("ood_too_aggressive"),
        "top_unstable_features": stability.get("top_unstable"),
        "top_drifted_features": drift.get("top_drifted"),
        "minimal_stable_feature_count": (minimal.get("recommended_minimal") or {}).get("feature_count"),
        "primary_root_cause": root.get("primary_root_cause"),
        "recommendations": root.get("recommendations"),
        "holdout_roi": {
            "always": (cmp_full.get("always_bet") or {}).get("roi"),
            "baseline": (cmp_full.get("baseline_portfolio") or {}).get("roi"),
            "overlay": (cmp_full.get("baseline_plus_similarity_overlay") or {}).get("roi"),
        },
        "holdout_drawdown": {
            "always": (cmp_full.get("always_bet") or {}).get("max_drawdown"),
            "baseline": (cmp_full.get("baseline_portfolio") or {}).get("max_drawdown"),
            "overlay": (cmp_full.get("baseline_plus_similarity_overlay") or {}).get("max_drawdown"),
        },
        "cosine_deserved_to_win": method_forensic.get("cosine_deserved_to_win"),
        "method_winner_on_validation": method_forensic.get("winner_on_validation"),
        "artifact_dir": str(out),
        "recommendation": "HOLD_SIMILARITY_OVERLAY — forensic complete; do not activate without owner approval",
    }
    _write_json(out / "validation_report.json", summary)

    md = _dashboard_md(summary, root, fo, stability, drift, minimal)
    _write_text(out / "owner_feature_stability_dashboard.md", md)
    _write_text(out / "owner_feature_stability_dashboard.html", _dashboard_html(summary))
    report = _final_report(summary, root, ood_rep, minimal, method_forensic, contrib)
    _write_text(out / "BETTING_DAY_FEATURE_STABILITY_FORENSIC_REPORT.md", report)
    Path("BETTING_DAY_FEATURE_STABILITY_FORENSIC_REPORT.md").write_text(report, encoding="utf-8")
    return summary


def _dashboard_md(summary, root, fo, stability, drift, minimal) -> str:
    return "\n".join(
        [
            "# Owner Feature Stability & OOD Forensic Dashboard",
            "",
            f"- Status: `{summary.get('status')}`",
            f"- Primary root cause: `{summary.get('primary_root_cause')}`",
            f"- False OOD: `{fo.get('false_ood')}` / True OOD: `{fo.get('true_ood')}`",
            f"- False alarm rate: `{fo.get('false_alarm_rate')}`",
            f"- OOD too aggressive: `{fo.get('ood_too_aggressive')}`",
            f"- Minimal stable feature count: `{summary.get('minimal_stable_feature_count')}`",
            "",
            "## Top unstable features",
            "",
            ", ".join(f"`{x}`" for x in (stability.get("top_unstable") or [])[:10]),
            "",
            "## Top drifted features",
            "",
            ", ".join(f"`{x}`" for x in (drift.get("top_drifted") or [])[:10]),
            "",
            "## Recommendations",
            "",
        ]
        + [f"- **{r['priority']}**: {r['recommendation']}" for r in (root.get("recommendations") or [])]
        + ["", "**NOT DEPLOYED**", ""]
    )


def _dashboard_html(summary: dict[str, Any]) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>Feature Stability Forensic</title>
<style>body{{font-family:Georgia,serif;background:#101820;color:#e8eef4;margin:2rem}}
h1{{color:#f0a070}}.card{{background:#1b2630;padding:1rem;margin:1rem 0;border-left:4px solid #f0a070}}
code{{color:#f0c674}}</style></head><body>
<h1>Betting Day Feature Stability Forensic</h1>
<div class="card"><strong>Status:</strong> <code>{summary.get('status')}</code><br/>
<strong>Primary root cause:</strong> <code>{summary.get('primary_root_cause')}</code><br/>
<strong>False OOD:</strong> <code>{summary.get('false_ood_count')}</code><br/>
<strong>Minimal features:</strong> <code>{summary.get('minimal_stable_feature_count')}</code><br/>
<strong>Deployment:</strong> NOT DEPLOYED</div>
<div class="card"><h2>Holdout ROI</h2>
<pre>{json.dumps(summary.get('holdout_roi'), indent=2)}</pre></div>
</body></html>
"""


def _final_report(summary, root, ood_rep, minimal, method_forensic, contrib) -> str:
    return "\n".join(
        [
            "# BETTING_DAY_FEATURE_STABILITY_FORENSIC_REPORT",
            "",
            f"**Status:** `{summary.get('status')}`  ",
            f"**Baseline commit:** `{BASELINE_COMMIT}`  ",
            "**Deployment:** NOT DEPLOYED",
            "",
            "## Verdict",
            "",
            "Similarity Overlay remains on HOLD. This audit explains ROI deterioration without changing any locked policy.",
            "",
            f"**Primary root cause:** `{summary.get('primary_root_cause')}`",
            "",
            "## Holdout snapshot",
            "",
            f"- Always / Baseline / Overlay ROI: `{summary.get('holdout_roi')}`",
            f"- Drawdowns: `{summary.get('holdout_drawdown')}`",
            f"- OOD days analyzed: `{ood_rep.get('n_ood_days')}`",
            f"- False OOD: `{summary.get('false_ood_count')}`",
            f"- Missed profit (eval): `{ood_rep.get('total_missed_profit')}`",
            f"- Avoided loss (eval): `{ood_rep.get('total_avoided_loss')}`",
            "",
            "## Feature drift / instability",
            "",
            f"- Top unstable: `{summary.get('top_unstable_features')}`",
            f"- Top drifted: `{summary.get('top_drifted_features')}`",
            f"- Minimal stable feature count: `{summary.get('minimal_stable_feature_count')}`",
            "",
            "## Method forensic",
            "",
            f"- Locked method: cosine / K=10",
            f"- Cosine deserved win on validation: `{method_forensic.get('cosine_deserved_to_win')}`",
            f"- Validation winner: `{method_forensic.get('winner_on_validation')}`",
            "",
            "## Component contribution",
            "",
            "```json",
            json.dumps(contrib.get("attributions"), indent=2),
            "```",
            "",
            "## Ranked failure causes",
            "",
            "```json",
            json.dumps(root.get("ranked_causes"), indent=2),
            "```",
            "",
            "## Recommendations (NOT implemented)",
            "",
            "```json",
            json.dumps(root.get("recommendations"), indent=2),
            "```",
            "",
            "**NOT DEPLOYED**",
            "",
        ]
    )
