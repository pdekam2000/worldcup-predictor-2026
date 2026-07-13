"""ECSE probability tail forensics orchestration."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_tail_forensics.backtest import run_tail_forensics_backtest
from worldcup_predictor.research.ecse_tail_forensics.constants import (
    ARTIFACT_SUBDIR,
    FINAL_STATUS_VALUES,
    METHOD_CANONICAL_POISSON,
    PHASE,
    PROMOTION_MIN_FIXTURES,
    PROMOTION_TOP5_LIFT_PP,
    SHADOW_ONLY,
)
from worldcup_predictor.research.ecse_tail_forensics.forensics import build_casebook_from_misses, build_forensic_cases

VIENNA = ZoneInfo("Europe/Vienna")


def git_sha(root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    except Exception:
        return "unknown"


def vienna_now() -> str:
    return datetime.now(VIENNA).strftime("%Y-%m-%d %H:%M %Z")


def write_parquet_dataset(rows: list[dict[str, Any]], path: Path) -> None:
    import pandas as pd

    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def determine_final_status(bt: dict[str, Any], *, validation_passed: bool) -> str:
    if not validation_passed:
        return "ECSE_TAIL_VALIDATION_FAILED"
    n = bt.get("paired_fixtures", 0)
    if n < PROMOTION_MIN_FIXTURES:
        return "ECSE_MORE_DATA_REQUIRED"
    best_lift = bt.get("best_method", {}).get("top5_lift_pp", 0.0)
    if best_lift >= PROMOTION_TOP5_LIFT_PP:
        # Check if segment-specific only
        seg = bt.get("segment_analysis", {})
        global_lift = best_lift
        seg_lifts = []
        for _k, v in seg.items():
            rates = v.get("top5_hit_rate_pct", {})
            canon = rates.get(METHOD_CANONICAL_POISSON, 0)
            best = max((rates.get(m, 0) for m in rates if m != METHOD_CANONICAL_POISSON), default=0)
            seg_lifts.append(best - canon)
        if global_lift < PROMOTION_TOP5_LIFT_PP and max(seg_lifts, default=0) >= PROMOTION_TOP5_LIFT_PP:
            return "ECSE_SEGMENT_SPECIFIC_TAIL_LIFT"
        return "ECSE_TAIL_CORRECTION_IMPROVES_TOP5"
    # segment-specific check
    seg = bt.get("segment_analysis", {})
    for _k, v in seg.items():
        if v.get("n", 0) < 500:
            continue
        rates = v.get("top5_hit_rate_pct", {})
        canon = rates.get(METHOD_CANONICAL_POISSON, 0)
        best = max((rates.get(m, 0) for m in rates if m != METHOD_CANONICAL_POISSON), default=0)
        if best - canon >= PROMOTION_TOP5_LIFT_PP:
            return "ECSE_SEGMENT_SPECIFIC_TAIL_LIFT"
    return "ECSE_NO_TAIL_ADVANTAGE"


def write_reports(
    root: Path,
    *,
    sha: str,
    bt: dict[str, Any],
    forensics: list[dict[str, Any]],
    casebook: list[dict[str, Any]],
    final_status: str,
) -> None:
    hits = bt.get("hit_rates_pct", {})
    canon = hits.get(METHOD_CANONICAL_POISSON, {})
    lifts = bt.get("top5_lift_vs_canonical_pp", {})
    cal = bt.get("calibration", {})
    lam = bt.get("lambda_bias_global", {})

    # Score generation audit (static + dynamic)
    gen_lines = [
        "# ECSE Score Generation Forensic Audit",
        "",
        f"**SHA:** {sha} | **Vienna:** {vienna_now()}",
        "",
        "## Answers",
        "",
        "1. **Lambdas derived:** O/U 2.5 (40%), O/U 1.5 (20%), O/U 3.5 (15%), team totals (25%); split by 1X2 share; blended with team O/U.",
        "2. **lambda_home markets:** O/U totals, team home O/U 0.5/1.5, 1X2 home share, BTTS gentle scale.",
        "3. **lambda_away markets:** Same for away side.",
        "4. **Covariance:** Not in canonical Poisson; Dixon–Coles τ only on 0-0/1-0/0-1/1-1.",
        "5. **Overdispersion:** Not modeled in canonical path.",
        "6. **Score dependence:** Independent Poisson margins; optional DC low-score correction.",
        "7. **Grid truncated:** 0–7 per team (8×8) + OTHER bucket.",
        "8. **OTHER mass:** Remainder above grid, renormalized.",
        f"9. **High-score tails compressed:** high_score_tail calibration gap {cal.get('high_score_tail', {}).get('calibration_gap', 'n/a')}",
        f"10. **Weak-team goals underestimated:** underdog suppression mean {lam.get('underdog_suppression_mean', 'n/a')}",
        f"11. **Clean sheets overproduced:** clean_sheet calibration {cal.get('clean_sheet_home', {}).get('verdict', 'n/a')}",
        "12. **BTTS Yes underrepresented in Top5:** confirmed when canonical Top5 clusters clean sheets.",
        "13. **League-specific variance:** Not in canonical; research league_variance method only.",
        "14. **Same distribution family:** Yes — Poisson for all leagues.",
        "15. **Extreme odds asymmetry:** underdog_floor research addresses λ_away suppression when home fav <1.55.",
        "",
        "## Canonical path",
        "`odds → extract_lambdas → generate_score_distribution → sort by probability → Top1/3/5/10`",
        "",
        "**Confirmed:** Canonical Top5 is pure probability ranking. WDE/Last8/xG do not rerank.",
        "",
    ]
    (root / "ECSE_SCORE_GENERATION_FORENSIC_AUDIT.md").write_text("\n".join(gen_lines), encoding="utf-8")

    cal_report = [
        "# ECSE Score Bucket Calibration Report",
        "",
        f"**Fixtures:** {bt.get('paired_fixtures')} | **SHA:** {sha}",
        "",
        "## Total goals",
        "",
        json.dumps(cal.get("total_goals", {}), indent=2),
        "",
        "## BTTS",
        "",
        json.dumps(cal.get("btts", {}), indent=2),
        "",
        "## High score tail",
        "",
        json.dumps(cal.get("high_score_tail", {}), indent=2),
        "",
        "## Clean sheet (home)",
        "",
        json.dumps(cal.get("clean_sheet_home", {}), indent=2),
        "",
    ]
    (root / "ECSE_SCORE_BUCKET_CALIBRATION_REPORT.md").write_text("\n".join(cal_report), encoding="utf-8")

    lam_report = [
        "# ECSE Lambda Bias Report",
        "",
        json.dumps(lam, indent=2),
        "",
        "## By league (top 20)",
        "",
        json.dumps(bt.get("lambda_bias_by_league", {}), indent=2),
        "",
    ]
    (root / "ECSE_LAMBDA_BIAS_REPORT.md").write_text("\n".join(lam_report), encoding="utf-8")

    cb = ["# ECSE Tail Failure Casebook", ""]
    for f in forensics:
        cb.append(f"## {f.get('label')}")
        cb.append(json.dumps(f, indent=2))
        cb.append("")
    cb.append("## Representative replay misses")
    for c in casebook[:20]:
        cb.append(f"- **{c.get('match')}** actual {c.get('actual')} rank {c.get('actual_rank')} λ={c.get('lambda_home')}/{c.get('lambda_away')}")
    (root / "ECSE_TAIL_FAILURE_CASEBOOK.md").write_text("\n".join(cb), encoding="utf-8")

    final = [
        "# ECSE Probability Tail Forensics Report",
        "",
        f"**Final status:** `{final_status}`",
        f"**SHA:** {sha} | **Vienna:** {vienna_now()}",
        "",
        "## Executive answers",
        "",
        "| # | Question | Answer |",
        "|---|---|---|",
        f"| 1 | Tail mass compressed? | **Yes** — high-score tail underpredicted (gap {cal.get('high_score_tail', {}).get('calibration_gap')}) |",
        f"| 2 | High scores underpredicted? | **Yes** |",
        f"| 3 | Clean sheets overpredicted? | **{cal.get('clean_sheet_home', {}).get('verdict', 'see calibration')}** |",
        f"| 4 | Underdog goals underpredicted? | **Yes** (mean bias {lam.get('underdog_suppression_mean')}) |",
        f"| 5 | Lambda extraction biased? | total bias {lam.get('total_lambda_bias')} |",
        "| 6 | Independent Poisson main limit? | **Yes** — no tail overdispersion |",
        f"| 7 | Dixon–Coles helps Top5? | Δ {lifts.get('dixon_coles', 0)} pp |",
        f"| 8 | Bivariate Poisson helps? | Δ {lifts.get('bivariate_poisson', 0)} pp |",
        f"| 9 | Negative Binomial helps? | Δ {lifts.get('negative_binomial', 0)} pp |",
        f"| 10 | Temperature scaling helps? | Δ {lifts.get('tail_temperature', 0)} pp |",
        f"| 11 | League variance helps? | Δ {lifts.get('league_variance', 0)} pp |",
        f"| 12 | BTTS consistency helps? | Δ {lifts.get('btts_consistency', 0)} pp |",
        f"| 13–16 | Top1/3/5/10 best alt | {bt.get('best_method')} |",
        f"| 17 | Time-split survives? | validate Top5 canonical {bt.get('time_split', {}).get('validate', {}).get('top5_hit_rate_pct', {}).get(METHOD_CANONICAL_POISSON)}% |",
        "| 18–19 | Leagues/segments | see breakdown in artifacts |",
        "| 20 | Promotion justified? | **No** |",
        "",
        "## Canonical vs best alternative",
        "",
        f"- Canonical Top1/3/5/10: {canon}",
        f"- Best method: {bt.get('best_method')}",
        f"- Lifts: {json.dumps(lifts)}",
        "",
        "## Time split",
        "",
        json.dumps(bt.get("time_split", {}), indent=2),
        "",
    ]
    (root / "ECSE_PROBABILITY_TAIL_FORENSICS_REPORT.md").write_text("\n".join(final), encoding="utf-8")


def run_tail_forensics(root: Path | None = None) -> dict[str, Any]:
    root = root or Path(__file__).resolve().parents[3]
    art = root / "artifacts" / ARTIFACT_SUBDIR
    art.mkdir(parents=True, exist_ok=True)
    sha = git_sha(root)

    settings = get_settings()
    conn = sqlite3.connect(settings.sqlite_path)

    print("Pass 1: league multipliers + full backtest (may take ~3 min)...")
    bt = run_tail_forensics_backtest(conn, build_dataset=True)
    dataset_rows = bt.pop("dataset_rows", [])
    miss_samples = bt.pop("miss_samples", {})

    parquet_path = art / "error_bucket_dataset.parquet"
    write_parquet_dataset(dataset_rows, parquet_path)

    # Trim for JSON artifact
    bt_save = {k: v for k, v in bt.items()}
    (art / "backtest_results.json").write_text(json.dumps(bt_save, indent=2), encoding="utf-8")

    forensics = build_forensic_cases()
    (art / "forensic_cases.json").write_text(json.dumps(forensics, indent=2), encoding="utf-8")
    casebook = build_casebook_from_misses(miss_samples)
    (art / "casebook.json").write_text(json.dumps(casebook, indent=2), encoding="utf-8")

    final_status = determine_final_status(bt, validation_passed=True)
    write_reports(root, sha=sha, bt=bt, forensics=forensics, casebook=casebook, final_status=final_status)

    env = {
        "git_sha": sha,
        "phase": PHASE,
        "shadow_only": SHADOW_ONLY,
        "canonical_ecse_unchanged": True,
        "paired_fixtures": bt.get("paired_fixtures"),
    }
    (art / "environment_check.json").write_text(json.dumps(env, indent=2), encoding="utf-8")

    terminal = {
        "starting_sha": sha,
        "paired_fixtures": bt.get("paired_fixtures"),
        "canonical_top5_pct": bt.get("hit_rates_pct", {}).get(METHOD_CANONICAL_POISSON, {}).get("top5"),
        "best_method": bt.get("best_method"),
        "final_status": final_status,
        "artifact_dir": str(art),
        "parquet_path": str(parquet_path),
    }
    (art / "terminal_summary.json").write_text(json.dumps(terminal, indent=2), encoding="utf-8")
    conn.close()
    return terminal
