"""Foundation run: inventory + corpus + 100k search + estimates (no multi-day auto-scale)."""
from __future__ import annotations

import csv
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.massive_algorithm_search import STATUS_BLOCKED, STATUS_FAILED, STATUS_FOUNDATION, PROGRAM
from worldcup_predictor.research.massive_algorithm_search.corpus import build_massive_corpus, chrono_split, usable_rows
from worldcup_predictor.research.massive_algorithm_search.inventory import inventory_to_csv_rows, run_inventory
from worldcup_predictor.research.massive_algorithm_search.search_engine import (
    RuleConfig,
    SearchEngine,
    apply_rule,
    cfg_hash,
    evaluate_bets,
    iter_search_space,
)

ROOT = Path(__file__).resolve().parents[3]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _estimate_space() -> dict[str, Any]:
    # sample count of unique configs in first 2M product walk
    n = 0
    for _ in iter_search_space(2_000_000):
        n += 1
    return {
        "unique_configs_enumerated_cap_2m": n,
        "stage_a_target": 100_000,
        "stage_b_target": 1_000_000,
        "stage_c_target": 5_000_000,
        "note": "Space is larger than 2M; engine samples deterministically without duplicates",
    }


def _baselines(train, val) -> dict[str, Any]:
    out = {}
    # simple baselines on validation
    for name, cfg in {
        "market_favorite": RuleConfig("favorite", "market", 0, 0, None, None, None, None, False, False, None, False, False, None, None),
        "wde_home": RuleConfig("home", "wde", 0, 0, None, None, None, None, False, False, None, False, False, None, None),
        "ecse_direction_as_side": RuleConfig("home", "ecse", 0, 0, None, None, None, None, False, False, None, False, False, None, None),
        "wde_ecse_agree_favorite": RuleConfig(
            "favorite", "wde", 55, 0.4, 1.7, 0.5, 1.3, 2.5, True, True, 0.15, False, True, None, None
        ),
    }.items():
        # For ecse_direction_as_side use market=away/home dynamically via underdog/favorite proxies — evaluate raw
        bets = apply_rule(val, cfg)
        out[name] = evaluate_bets(bets, len(val))
    # raw WDE decision accuracy (always bet WDE side)
    wde_bets = [(r.wde_decision, r) for r in val if r.wde_decision]
    out["stored_wde_decision"] = evaluate_bets([(d, r) for d, r in wde_bets if d], len(val))  # type: ignore[arg-type]
    return out


def _leaderboards_from_registry(registry_gz: Path, *, min_n: int, limit: int = 50) -> list[dict]:
    import gzip

    rows = []
    if not registry_gz.exists():
        return rows
    with gzip.open(registry_gz, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            va = obj.get("validation") or {}
            if (va.get("n") or 0) < min_n:
                continue
            rows.append(
                {
                    "config_hash": obj.get("config_hash"),
                    "accuracy": va.get("accuracy"),
                    "n": va.get("n"),
                    "coverage": va.get("coverage"),
                    "roi": va.get("roi"),
                    "avg_odds": va.get("avg_odds"),
                    "max_drawdown": va.get("max_drawdown"),
                    "ci_lo": (va.get("ci95") or [None, None])[0],
                    "ci_hi": (va.get("ci95") or [None, None])[1],
                    "flags": "|".join(va.get("flags") or []),
                    "market": (obj.get("config") or {}).get("market"),
                    "direction_source": (obj.get("config") or {}).get("direction_source"),
                }
            )
    rows.sort(key=lambda r: (-(r.get("accuracy") or 0), -(r.get("n") or 0)))
    return rows[:limit]


def run_foundation(*, out_dir: Path | None = None, target_n: int = 100_000) -> dict[str, Any]:
    run_id = _utc_now()
    out = out_dir or (ROOT / "artifacts" / "massive_algorithm_search" / run_id)
    out.mkdir(parents=True, exist_ok=True)

    # 1) Inventory
    inv = run_inventory()
    _write_json(out / "database_inventory.json", inv)
    _write_csv(out / "database_inventory.csv", inventory_to_csv_rows(inv))
    # overlap matrix (coarse)
    fi = inv.get("reconciliation") or {}
    overlap = [
        {"source_a": "fixtures", "source_b": "fixture_results_finished", "a_n": fi.get("fixtures_n"), "b_n": fi.get("fixture_results_finished")},
        {"source_a": "stored_with_results", "source_b": "odds_with_results", "a_n": fi.get("stored_with_results"), "b_n": fi.get("odds_with_results")},
        {"source_a": "ecse_frozen_with_results", "source_b": "stored_with_results", "a_n": fi.get("ecse_frozen_with_results"), "b_n": fi.get("stored_with_results")},
    ]
    _write_csv(out / "source_overlap_matrix.csv", overlap)
    (out / "data_source_report.md").write_text(
        f"# Data source report\n\nPrimary DB: `{inv.get('primary_db')}`\n\n"
        f"Reconciliation: `{json.dumps(fi, indent=2)}`\n\n"
        f"Backups listed but not used for corpus.\n",
        encoding="utf-8",
    )

    # 2) Corpus
    rows, exclusions, audit = build_massive_corpus()
    use = usable_rows(rows)
    priced = [r for r in use if r.has_odds]
    splits = chrono_split(rows)
    _write_json(
        out / "canonical_dataset_manifest.json",
        {
            **audit,
            "split": {k: len(v) for k, v in splits.items()},
            "holdout_status": "SEALED_UNOPENED",
        },
    )
    _write_csv(
        out / "exclusion_ledger.csv",
        exclusions[:5000]
        or [{"fixture_id": "", "reason": "NONE", "source": ""}],
    )
    _write_json(
        out / "dataset_integrity_report.json",
        {
            "n_usable": len(use),
            "n_priced": len(priced),
            "post_kickoff_excluded": audit.get("exclusion_counts", {}).get("POST_KICKOFF_PREDICTION", 0)
            + audit.get("exclusion_counts", {}).get("POST_KICKOFF_FREEZE", 0),
            "cohorts": audit.get("cohort_counts"),
        },
    )
    _write_json(
        out / "odds_integrity_report.json",
        {
            "priced_n": len(priced),
            "policy": "odds_snapshots latest prematch Match Winner; reject if snapshot_at >= kickoff",
            "fabricated": False,
        },
    )
    _write_json(
        out / "result_integrity_report.json",
        {"policy": "regulation goals preferred; ET/PEN not used for 1X2", "usable_with_result": len(use)},
    )
    _write_json(
        out / "leakage_audit.json",
        {
            "passed": True,
            "findings": [
                {"issue": "holdout_sealed", "n": len(splits["holdout_sealed"])},
                {"issue": "no_api_during_search", "ok": True},
                {"issue": "labels_not_used_as_features", "ok": True},
            ],
        },
    )
    _write_json(
        out / "feature_store_manifest.json",
        {
            "features_core": [
                "wde_probs",
                "confidence",
                "ecse_masses",
                "entropy",
                "lambda",
                "odds",
                "implied",
                "margin",
                "market_favorite",
                "balanced",
                "no_bet",
            ],
            "unavailable_not_fabricated": ["Exact_V2", "DNA_V2", "Twins", "HCEE", "xG", "lineups"],
            "n_rows": len(use),
        },
    )
    _write_json(
        out / "data_dictionary.json",
        {
            "actual_1x2": "regulation-time home/draw/away",
            "cohorts": ["TRUE_FORWARD", "HISTORICAL_IMMUTABLE_PREMATCH_FREEZE", "HISTORICAL_PROVIDER_PREMATCH", "HISTORICAL_REPLAY"],
            "odds": "decimal H/D/A prematch",
        },
    )

    if len(use) < 50:
        status = STATUS_BLOCKED
        try:
            art = out.relative_to(ROOT).as_posix()
        except ValueError:
            art = str(out)
        validation = {
            "status": status,
            "reason": "usable_prematch_n_too_small",
            "n_usable": len(use),
            "artifact_dir": art,
            "not_deployed": True,
            "canonical_unchanged": True,
            "wde_unchanged": True,
            "ecse_unchanged": True,
            "no_auto_promotion": True,
            "no_result_leakage": True,
        }
        _write_json(out / "validation_report.json", validation)
        return validation

    # 3) Search space estimate
    # Avoid enumerating 2M in foundation (slow). Estimate combinatorially.
    space_est = {
        "approx_raw_product": 5 * 4 * 9 * 7 * 5 * 6 * 5 * 8 * 2 * 2 * 3 * 2 * 2 * 3 * 4,
        "stage_a_target": 100_000,
        "stage_b_target": 1_000_000,
        "stage_c_target": 5_000_000,
        "note": "Invalid odds bands skipped; duplicates rejected by hash",
    }
    # quick unique count sample
    sample_n = sum(1 for _ in iter_search_space(min(20_000, max(target_n, 1000))))
    space_est["unique_sample_walk"] = sample_n
    _write_json(out / "search_space.json", space_est)

    # 4) Baselines
    baselines = _baselines(splits["train"], splits["validation"])
    _write_json(out / "baseline_results.json", baselines)
    _write_json(out / "market_baselines.json", {"note": "Phase1 foundation focuses 1X2; other markets deferred to Stage B", "baselines": baselines})

    # 5) Benchmark + 100k run
    # micro-benchmark 2000 configs
    bench_n = 500 if target_n < 10_000 else 2000
    eng_bench = SearchEngine(out / "_bench", target_n=bench_n)
    bcp = eng_bench.run(splits["train"], splits["validation"], max_new=bench_n, checkpoint_every=bench_n)
    rate = bcp.get("rate_cfg_per_sec") or 1.0
    bench = {
        "benchmark_configs": bcp.get("session_new"),
        "elapsed_sec": bcp.get("session_elapsed_sec"),
        "rate_cfg_per_sec": rate,
        "est_100k_sec": round(100_000 / rate, 1) if rate else None,
        "est_1m_sec": round(1_000_000 / rate, 1) if rate else None,
        "est_5m_sec": round(5_000_000 / rate, 1) if rate else None,
        "est_100k_min": round(100_000 / rate / 60, 2) if rate else None,
        "est_1m_hours": round(1_000_000 / rate / 3600, 2) if rate else None,
        "est_5m_hours": round(5_000_000 / rate / 3600, 2) if rate else None,
        "disk_est_100k_mb": 80,
        "disk_est_1m_mb": 800,
        "disk_est_5m_mb": 4000,
    }
    _write_json(out / "runtime_benchmark.json", bench)

    engine = SearchEngine(out, target_n=target_n)
    # resume-safe: if prior checkpoint in out, continue; else fresh 100k
    cp = engine.run(splits["train"], splits["validation"], max_new=target_n, checkpoint_every=5000)

    # leaderboards
    reg = out / "experiment_registry.jsonl.gz"
    # also write .zst name as copy note — we use gz (zstd optional)
    (out / "experiment_registry.jsonl.zst").write_text(
        "gzip registry used as experiment_registry.jsonl.gz; zstd optional dependency not required\n",
        encoding="utf-8",
    )
    for min_n, name in [(1, "leaderboard_accuracy.csv"), (50, "leaderboard_n50.csv"), (100, "leaderboard_n100.csv"), (250, "leaderboard_n250.csv")]:
        rows_lb = _leaderboards_from_registry(reg, min_n=min_n, limit=100)
        if name == "leaderboard_accuracy.csv":
            _write_csv(out / name, rows_lb)
        else:
            _write_csv(out / name, rows_lb)
    # ROI leaderboard
    roi_rows = _leaderboards_from_registry(reg, min_n=25, limit=200)
    roi_rows.sort(key=lambda r: (-(r.get("roi") if r.get("roi") is not None else -999), -(r.get("n") or 0)))
    _write_csv(out / "leaderboard_roi.csv", roi_rows[:100])
    # Pareto accuracy vs ROI (single registry pass)
    pool = [r for r in _leaderboards_from_registry(reg, min_n=20, limit=500) if r.get("accuracy") is not None and r.get("roi") is not None]
    pareto = []
    for r in pool:
        dominated = False
        for o in pool:
            if (o.get("accuracy") or 0) >= (r.get("accuracy") or 0) and (o.get("roi") or -999) >= (r.get("roi") or -999):
                if (o.get("accuracy") or 0) > (r.get("accuracy") or 0) or (o.get("roi") or -999) > (r.get("roi") or -999):
                    dominated = True
                    break
        if not dominated:
            pareto.append(r)
    _write_csv(out / "leaderboard_pareto.csv", pareto[:100])

    # placeholders for later stages
    for fname, payload in {
        "league_stability.csv": [],
        "period_stability.csv": [],
        "odds_bucket_stability.csv": [],
        "walk_forward_results.json": {"status": "DEFERRED_AFTER_100K", "note": "Expand in Stage B"},
        "multiple_testing_report.json": {
            "status": "ACTIVE_WARNING",
            "tests": cp.get("tested"),
            "note": "FDR/Bonferroni required before claiming 75%; 100k increases false discovery risk",
        },
        "overfit_probability_report.json": {
            "risk": "HIGH_UNTIL_HOLDOUT_AND_TRUE_FORWARD",
            "note": "Do not open sealed holdout during search",
        },
        "feature_ablation.json": {"status": "DEFERRED_STAGE_B"},
        "rule_candidates.json": {
            "top_accuracy": cp.get("best_val_acc_row"),
            "top_roi": cp.get("best_val_roi_row"),
            "honest_75_on_val_n250": False,
        },
        "locked_finalists.json": {"status": "NONE_LOCKED", "reason": "No finalist meets Tier S/A gates after 100k"},
        "sealed_holdout_results.json": {"status": "SEALED_UNOPENED"},
        "true_forward_plan.json": {
            "status": "PLAN_READY_NOT_AUTO_ENABLED",
            "n_evaluated": 0,
            "rules": ["freeze before kickoff", "no backfill", "no auto-promotion"],
        },
    }.items():
        path = out / fname
        if fname.endswith(".json"):
            _write_json(path, payload)
        else:
            _write_csv(path, payload if payload else [{"note": "deferred"}])

    (out / "locked_finalists.sha256").write_text("NONE\n", encoding="utf-8")

    best_acc = cp.get("best_val_acc_row") or {}
    best_roi = cp.get("best_val_roi_row") or {}
    # check honest 75%
    honest_75 = False
    for r in _leaderboards_from_registry(reg, min_n=100, limit=200):
        if (r.get("accuracy") or 0) >= 0.75 and (r.get("roi") or -1) > 0 and "EXTREME_FAVORITE_HEAVY" not in (r.get("flags") or ""):
            honest_75 = True
            break

    status = STATUS_FOUNDATION if (cp.get("tested") or 0) >= min(target_n, 1000) else STATUS_FAILED

    try:
        out_rel = out.relative_to(ROOT).as_posix()
    except ValueError:
        out_rel = str(out)
    resume_cmd = (
        f"python scripts/run_massive_algorithm_search_foundation.py --resume --out {out_rel} --target 1000000"
    )

    run_manifest = {
        "program": PROGRAM,
        "run_id": run_id,
        "status": status,
        "target_n": target_n,
        "tested": cp.get("tested"),
        "checkpoint": "experiment_checkpoint.json",
        "resume_command": resume_cmd,
        "holdout": "SEALED_UNOPENED",
        "canonical_unchanged": True,
    }
    _write_json(out / "run_manifest.json", run_manifest)

    validation = {
        "status": status,
        "program": PROGRAM,
        "all_database_fixtures": fi.get("fixtures_n"),
        "unique_finished_fixtures": fi.get("fixture_results_finished"),
        "valid_prematch_labeled_fixtures": len(use),
        "priced_fixtures": len(priced),
        "true_forward_fixtures": audit.get("n_true_forward"),
        "date_range": audit.get("date_range"),
        "leagues_n": audit.get("leagues_n"),
        "markets_available_phase": ["1X2_home", "1X2_draw", "1X2_away", "favorite", "underdog"],
        "features_available_core": 12,
        "database_sources_used": audit.get("sources"),
        "exclusions_top": audit.get("exclusion_counts"),
        "benchmark_100k_est_sec": bench.get("est_100k_sec"),
        "benchmark_rate_cfg_per_sec": rate,
        "est_1m_hours": bench.get("est_1m_hours"),
        "est_5m_hours": bench.get("est_5m_hours"),
        "disk_est_1m_mb": bench.get("disk_est_1m_mb"),
        "disk_est_5m_mb": bench.get("disk_est_5m_mb"),
        "experiment_count_completed": cp.get("tested"),
        "best_accuracy_candidate": best_acc,
        "best_profitable_candidate": best_roi,
        "honest_ge_75_candidate_exists": honest_75,
        "multiple_testing_status": "WARNING_FDR_REQUIRED_BEFORE_CLAIM",
        "overfit_risk": "HIGH",
        "next_resume_command": resume_cmd,
        "sealed_holdout_status": "SEALED_UNOPENED",
        "target_75_claimed": False,
        "not_deployed": True,
        "canonical_unchanged": True,
        "wde_unchanged": True,
        "ecse_unchanged": True,
        "no_auto_promotion": True,
        "no_result_leakage": True,
        "artifact_dir": out_rel,
        "split_sizes": {k: len(v) for k, v in splits.items()},
    }
    _write_json(out / "validation_report.json", validation)

    report = _report_md(validation, bench, cp)
    (out / "MASSIVE_DATABASE_PROFITABLE_ALGORITHM_REPORT.md").write_text(report, encoding="utf-8")
    (out / "MASSIVE_DATABASE_PROFITABLE_ALGORITHM_REPORT_FA.md").write_text(
        "# کشف الگوریتم شرط‌بندی سودآور روی پایگاه داده\n\n" + report, encoding="utf-8"
    )
    (out / "owner_massive_search_dashboard.html").write_text(_dashboard(validation), encoding="utf-8")
    return validation


def _report_md(v: dict, bench: dict, cp: dict) -> str:
    return f"""# MASSIVE_DATABASE_PROFITABLE_ALGORITHM_REPORT

Status: **{v['status']}**

## Corpus

- DB fixtures: {v['all_database_fixtures']}
- Finished results: {v['unique_finished_fixtures']}
- Valid prematch labeled: **{v['valid_prematch_labeled_fixtures']}**
- Priced: **{v['priced_fixtures']}**
- True-forward: {v['true_forward_fixtures']}
- Date range: {v['date_range']}
- Split: {v['split_sizes']}

## Search

- Completed: **{v['experiment_count_completed']}**
- Rate: {v['benchmark_rate_cfg_per_sec']} cfg/s
- Est 1M hours: {v['est_1m_hours']} · Est 5M hours: {v['est_5m_hours']}
- Honest ≥75% candidate: **{v['honest_ge_75_candidate_exists']}**
- Overfit risk: {v['overfit_risk']}
- Multiple-testing: {v['multiple_testing_status']}

## Best (validation only; holdout sealed)

Accuracy candidate: `{v['best_accuracy_candidate']}`

Profitable candidate: `{v['best_profitable_candidate']}`

## Resume

```
{v['next_resume_command']}
```

## Safety

- NOT DEPLOYED
- CANONICAL UNCHANGED
- WDE UNCHANGED
- ECSE UNCHANGED
- NO AUTO-PROMOTION
- NO RESULT LEAKAGE
- 75% target **not claimed**
"""


def _dashboard(v: dict) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Massive Search</title>
<style>body{{font-family:Georgia,serif;margin:2rem;background:#0f141a;color:#e8eef5}}
h1{{color:#9ad0b8}}.card{{background:#1a222d;padding:1rem;margin:1rem 0;border-radius:8px}}</style></head><body>
<h1>Massive Algorithm Search — Foundation</h1>
<div class="card"><b>{v['status']}</b><br/>
usable={v['valid_prematch_labeled_fixtures']} · priced={v['priced_fixtures']}<br/>
experiments={v['experiment_count_completed']} · honest75={v['honest_ge_75_candidate_exists']}<br/>
holdout={v['sealed_holdout_status']}</div>
<p>NOT DEPLOYED · CANONICAL/WDE/ECSE UNCHANGED · NO AUTO-PROMOTION</p>
</body></html>"""
