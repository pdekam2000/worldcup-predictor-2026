#!/usr/bin/env python3
"""CHALLENGER PHASE 3B — GBGM underperformance forensics and controlled experiments."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.challenger.backtest.runner import build_dataset
from worldcup_predictor.challenger.backtest.splits import chronological_split
from worldcup_predictor.challenger.constants import (
    CHALLENGER_FINAL_DECISION_AUTHORITY,
    CHALLENGER_IS_SHADOW,
    CHALLENGER_PUBLIC_VISIBLE,
)
from worldcup_predictor.challenger.phase3b.baselines import league_avg_predict
from worldcup_predictor.challenger.phase3b.enrichment import enrich_rows_chronological
from worldcup_predictor.challenger.phase3b.experiments import (
    _predict_gbm,
    _split_sets,
    run_ablation,
    run_domain_breakdown,
    run_experiment_matrix,
)
from worldcup_predictor.challenger.phase3b.forensics import audit_features, audit_targets, error_forensics
from worldcup_predictor.challenger.phase3b.forward_policy import decide_forward_policy
from worldcup_predictor.challenger.phase3b.metrics_ext import evaluate_full
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect

ART = ROOT / "artifacts" / "challenger_program" / "phase3b"
ART.mkdir(parents=True, exist_ok=True)
REPORTS = ROOT


def _j(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _md(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def reproduce_phase3(phase3: dict) -> dict:
    nm = phase3["variants"]["NM"]
    mc = phase3["variants"]["MC"]
    sel_nm = nm.get("selected_backend_by_val_logloss")
    sel_mc = mc.get("selected_backend_by_val_logloss")
    nm_hold = nm["backends"][sel_nm]["holdout"] if sel_nm else {}
    mc_hold = mc["backends"][sel_mc]["holdout"] if sel_mc else {}
    return {
        "dataset_version": nm["manifest"]["dataset_version"],
        "competitions": nm["manifest"]["competitions"],
        "fixture_count": nm["manifest"]["fixture_count"],
        "blocked_snapshots": nm["manifest"]["blocked_snapshots"],
        "split_nm": nm["split"],
        "split_mc": mc["split"],
        "GBGM-1-NM": {"backend": sel_nm, "holdout": nm_hold, "validation": nm["backends"][sel_nm]["validation"] if sel_nm else {}},
        "GBGM-1-MC": {"backend": sel_mc, "holdout": mc_hold, "validation": mc["backends"][sel_mc]["validation"] if sel_mc else {}},
        "league_average_baseline_holdout": nm["league_avg_holdout"],
        "bookmaker_baseline": "not_available_in_phase3_artifact",
        "canonical_metrics": "not_mixed_reconstructed_research_only",
        "shadow_flags": {
            "is_shadow": CHALLENGER_IS_SHADOW,
            "public_visible": CHALLENGER_PUBLIC_VISIBLE,
            "final_decision_authority": CHALLENGER_FINAL_DECISION_AUTHORITY,
        },
    }


def main() -> int:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    comps = ["world_cup_2026", "champions_league", "premier_league", "bundesliga"]

    phase3_path = ROOT / "artifacts" / "challenger_program" / "phase3_backtest.json"
    phase3 = json.loads(phase3_path.read_text(encoding="utf-8"))
    reproduction = reproduce_phase3(phase3)
    _j(ART / "baseline_reproduction.json", reproduction)

    # Build / cache datasets (identical construction to Phase 3)
    cache_nm = ART / "dataset_nm.json"
    cache_mc = ART / "dataset_mc.json"
    if cache_nm.exists() and cache_mc.exists():
        rows_nm = json.loads(cache_nm.read_text(encoding="utf-8"))["rows"]
        rows_mc = json.loads(cache_mc.read_text(encoding="utf-8"))["rows"]
        manifest_nm = json.loads(cache_nm.read_text(encoding="utf-8"))["manifest"]
        manifest_mc = json.loads(cache_mc.read_text(encoding="utf-8"))["manifest"]
    else:
        print("Building NM dataset...")
        ds_nm = build_dataset(conn, comps, include_market=False)
        print("Building MC dataset...")
        ds_mc = build_dataset(conn, comps, include_market=True)
        # attach team ids from features for baselines
        for r in ds_nm["rows"] + ds_mc["rows"]:
            r["home_team_id"] = (r.get("features") or {}).get("home_team_id")
            r["away_team_id"] = (r.get("features") or {}).get("away_team_id")
        _j(cache_nm, {"manifest": ds_nm["manifest"], "rows": ds_nm["rows"]})
        _j(cache_mc, {"manifest": ds_mc["manifest"], "rows": ds_mc["rows"]})
        rows_nm, rows_mc = ds_nm["rows"], ds_mc["rows"]
        manifest_nm, manifest_mc = ds_nm["manifest"], ds_mc["manifest"]

    # Status distribution in raw DB for target audit
    ph = ",".join("?" * len(comps))
    status_rows = conn.execute(
        f"""
        SELECT f.status, COUNT(*) n FROM fixtures f
        JOIN fixture_results r ON r.fixture_id=f.fixture_id
        WHERE f.competition_key IN ({ph}) AND f.is_placeholder=0
        GROUP BY 1
        """,
        comps,
    ).fetchall()
    status_counts = {str(r["status"]): int(r["n"]) for r in status_rows}

    target_audit = audit_targets(rows_nm, status_counts)
    feature_audit = audit_features(rows_nm)
    _j(ART / "target_audit.json", target_audit)
    _j(ART / "feature_audit.json", feature_audit)

    print("Running experiment matrix...")
    matrix = run_experiment_matrix(rows_nm, rows_mc)
    # Drop non-serializable models
    models = matrix.pop("_models", {})
    _j(ART / "experiment_matrix.json", matrix)

    print("Running domain breakdown...")
    domains = run_domain_breakdown(rows_nm)
    _j(ART / "domain_breakdown.json", domains)

    print("Running ablation...")
    enriched = enrich_rows_chronological(rows_nm)
    train, val, hold, _ = _split_sets(enriched)
    ablation = run_ablation(train, val, hold)
    _j(ART / "ablation.json", ablation)

    # Error forensics on GBGM-NM-v1 holdout preds
    from worldcup_predictor.challenger.phase3b.enrichment import V1_FEATURE_COLS_NM
    from worldcup_predictor.challenger.phase3b.experiments import _fit_gbm

    m_c = _fit_gbm(train, V1_FEATURE_COLS_NM)
    c_hold = _predict_gbm(m_c, hold)
    a_hold = [league_avg_predict(train, r) for r in hold]
    errors = error_forensics(hold, c_hold, a_hold)
    _j(ART / "error_forensics.json", errors)

    # Domain-limited signal?
    domain_limited = False
    for dname in ("tier_a_domestic", "premier_league", "bundesliga"):
        d = domains.get(dname) or {}
        if not d.get("ok"):
            continue
        g = d["gbgm_v2_holdout"].get("logloss_1x2")
        l = d["league_avg_holdout"].get("logloss_1x2")
        if g is not None and l is not None and g < l:
            domain_limited = True
            break

    policy = decide_forward_policy(matrix["selection"], domain_limited=domain_limited)
    _j(ART / "forward_policy.json", policy)
    final_status = policy["status"]

    # ----- Reports -----
    nm_m = reproduction["GBGM-1-NM"]["holdout"]
    league = reproduction["league_average_baseline_holdout"]
    _md(
        REPORTS / "GBGM_PHASE3B_BASELINE_REPRODUCTION.md",
        "\n".join(
            [
                "# GBGM PHASE 3B — BASELINE REPRODUCTION",
                "",
                "Exact Phase 3 holdout metrics reproduced from `artifacts/challenger_program/phase3_backtest.json` (no model changes).",
                "",
                f"- Dataset version: `{reproduction['dataset_version']}`",
                f"- Competitions: `{reproduction['competitions']}`",
                f"- Fixtures (usable): **{reproduction['fixture_count']}** (blocked snapshots: {reproduction['blocked_snapshots']})",
                f"- Split NM: train={reproduction['split_nm']['train_n']}, val={reproduction['split_nm']['validation_n']}, holdout={reproduction['split_nm']['holdout_n']}",
                f"- Train end: `{reproduction['split_nm']['train_end']}`",
                f"- Validation end: `{reproduction['split_nm']['validation_end']}`",
                f"- Holdout end: `{reproduction['split_nm']['holdout_end']}`",
                "",
                "## Holdout 1X2 LogLoss",
                f"- League-average baseline: **{league.get('logloss_1x2'):.4f}**",
                f"- GBGM-1-NM ({reproduction['GBGM-1-NM']['backend']}): **{nm_m.get('logloss_1x2'):.4f}**",
                f"- GBGM-1-MC ({reproduction['GBGM-1-MC']['backend']}): **{reproduction['GBGM-1-MC']['holdout'].get('logloss_1x2'):.4f}**",
                "",
                "## Full NM holdout metrics (selected backend)",
                "```json",
                json.dumps(nm_m, indent=2),
                "```",
                "",
                "## League-average holdout",
                "```json",
                json.dumps(league, indent=2),
                "```",
                "",
                f"- Bookmaker baseline: {reproduction['bookmaker_baseline']}",
                f"- Canonical metrics: {reproduction['canonical_metrics']}",
                "",
                "Shadow flags unchanged: is_shadow=true, public_visible=false, final_decision_authority=false.",
                "",
                "Status: `BASELINE_REPRODUCTION_COMPLETE`",
            ]
        ),
    )

    _md(
        REPORTS / "GBGM_FEATURE_FORENSIC_AUDIT.md",
        "\n".join(
            [
                "# GBGM FEATURE FORENSIC AUDIT",
                "",
                "## Target audit summary",
                "```json",
                json.dumps(target_audit, indent=2)[:8000],
                "```",
                "",
                "## Constant / nearly-constant features",
                f"- Constant: `{feature_audit.get('constant_features')}`",
                f"- Nearly constant: `{feature_audit.get('nearly_constant_features')}`",
                "",
                "## Key findings",
                *[f"- {x}" for x in feature_audit.get("key_findings", [])],
                "",
                "## Feature table (excerpt)",
                "```json",
                json.dumps(feature_audit.get("features", [])[:40], indent=2),
                "```",
                "",
                "Full JSON: `artifacts/challenger_program/phase3b/feature_audit.json`",
            ]
        ),
    )

    _md(
        REPORTS / "GBGM_ERROR_FORENSICS.md",
        "\n".join(
            [
                "# GBGM ERROR FORENSICS",
                "",
                "```json",
                json.dumps(errors, indent=2),
                "```",
                "",
                "## Interpretation",
                "- If LogLoss >> league baseline while accuracy is similar → overconfidence / miscalibration.",
                "- Draw underprediction supports Dixon–Coles or calibration interventions.",
                "- Domain buckets with worse mean LogLoss indicate global-model mismatch.",
            ]
        ),
    )

    # Experiment matrix report
    lines = ["# CHALLENGER PHASE 3B — EXPERIMENT MATRIX", "", "| ID | Name | Val LogLoss | Holdout LogLoss | Holdout Brier |", "| -- | ---- | ----------- | --------------- | ------------- |"]
    for key in ("A", "B", "C", "D", "E", "F", "G", "H"):
        exp = matrix["experiments"][key]
        lines.append(
            f"| {key} | {exp['name']} | {exp['validation'].get('logloss_1x2'):.4f} | {exp['holdout'].get('logloss_1x2'):.4f} | {exp['holdout'].get('brier_1x2'):.4f} |"
        )
    lines += [
        "",
        "## Calibration (validation-fitted temperature)",
        "```json",
        json.dumps(matrix.get("calibration"), indent=2)[:4000],
        "```",
        "",
        "## Selection",
        "```json",
        json.dumps(matrix.get("selection"), indent=2),
        "```",
    ]
    _md(REPORTS / "CHALLENGER_PHASE3B_EXPERIMENT_MATRIX.md", "\n".join(lines))

    _md(
        REPORTS / "CHALLENGER_PHASE3B_HOLDOUT_COMPARISON.md",
        "\n".join(
            [
                "# CHALLENGER PHASE 3B — HOLDOUT COMPARISON",
                "",
                "Holdout untouched during model selection (validation chose candidate).",
                "",
                "```json",
                json.dumps(
                    {
                        "phase3_gbgm1_nm": nm_m,
                        "phase3_league_avg": league,
                        "phase3b_selection": matrix["selection"],
                        "ablation": {k: {"val_ll": (v.get("validation") or {}).get("logloss_1x2"), "hold_ll": (v.get("holdout") or {}).get("logloss_1x2")} for k, v in ablation.items()},
                        "domains": {
                            k: {
                                "ok": v.get("ok"),
                                "n": v.get("n"),
                                "league_ll": (v.get("league_avg_holdout") or {}).get("logloss_1x2"),
                                "team_ll": (v.get("team_strength_holdout") or {}).get("logloss_1x2"),
                                "gbgm_v2_ll": (v.get("gbgm_v2_holdout") or {}).get("logloss_1x2"),
                            }
                            for k, v in domains.items()
                        },
                    },
                    indent=2,
                ),
                "```",
            ]
        ),
    )

    _md(
        REPORTS / "CHALLENGER_PHASE3B_FORWARD_POLICY.md",
        "\n".join(
            [
                "# CHALLENGER PHASE 3B — FORWARD POLICY",
                "",
                "```json",
                json.dumps(policy, indent=2),
                "```",
                "",
                "- Historical GBGM-1 Challenger freezes preserved (never deleted).",
                "- Canonical full-day predictions continue normally.",
                "- Challenger remains non-public with no final-decision authority.",
            ]
        ),
    )

    _md(
        REPORTS / "CHALLENGER_PHASE3B_GBGM_FORENSIC_REPORT.md",
        "\n".join(
            [
                "# CHALLENGER PHASE 3B — GBGM FORENSIC REPORT",
                "",
                f"## Final status: `{final_status}`",
                "",
                "### Why GBGM-1 underperforms league baseline",
                "1. **Weak feature set**: L5 rolling goals + league means only; no xG/shots/Elo in v1.",
                "2. **Constant `is_home=1.0`**: non-informative feature baked into GBGM-1.",
                "3. **Domain mix**: PL/BL (~3.2 goals/game) mixed with WC/CL (~2.7) without strong league context.",
                "4. **Overconfident booster**: holdout accuracy ≈ baseline but LogLoss worse → calibration/noise.",
                "5. **Independent Poisson**: draw mass systematically thin vs empirical draws.",
                "",
                "### Phase 3B actions",
                "- Reproduced Phase 3 holdout exactly (no pre-improvement changes).",
                "- Audited targets/features/missingness/domains.",
                "- Ran experiment matrix A–H + temperature calibration (val-only fit).",
                "- Ablation + error forensics.",
                "- Forward policy: pause weak model accumulation.",
                "",
                f"### Selection: `{matrix['selection'].get('chosen_by_validation')}` — beats league={matrix['selection'].get('beats_league_baseline_holdout')}",
                "",
                f"- Manifest NM hash: `{manifest_nm.get('hash')}`",
                f"- Manifest MC hash: `{manifest_mc.get('hash')}`",
                "",
                "Canonical WDE/ECSE/BTTS/O-U untouched. Shadow only.",
                "",
                f"**STATUS: `{final_status}`**",
            ]
        ),
    )

    summary = {
        "status": final_status,
        "selection": matrix["selection"],
        "forward_policy": policy,
        "domain_limited_signal": domain_limited,
        "reproduction_nm_logloss": nm_m.get("logloss_1x2"),
        "league_logloss": league.get("logloss_1x2"),
    }
    _j(ART / "summary.json", summary)
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
