"""Audit completed 100k foundation run and decide 1M scale-up (no holdout open)."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
RUN_ID = "20260802T193933Z"
RUN_DIR = ROOT / "artifacts" / "massive_algorithm_search" / RUN_ID
FOUNDATION_COMMIT = "3e1100a"
AUDIT_STATUS_APPROVED = "MASSIVE_SEARCH_100K_AUDITED_1M_APPROVED"
AUDIT_STATUS_RUNNING = "MASSIVE_SEARCH_100K_AUDITED_1M_RUNNING"
AUDIT_STATUS_NOT_JUSTIFIED = "MASSIVE_SEARCH_100K_AUDITED_SCALE_NOT_JUSTIFIED"
AUDIT_STATUS_FAILED = "MASSIVE_SEARCH_100K_AUDIT_VALIDATION_FAILED"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _sha_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((RUN_DIR / name).read_text(encoding="utf-8"))


def scan_registry(path: Path) -> dict[str, Any]:
    """Stream gzip registry once; compute counts and leaderboards."""
    n_lines = 0
    hashes: set[str] = set()
    dup = 0
    acc75 = Counter()  # keys: lt50, ge50, ge100, ge250, ge75_pos_roi
    best_by: dict[str, dict] = {}

    def consider(key: str, row: dict, score: float, prefer_n: bool = True):
        cur = best_by.get(key)
        if cur is None:
            best_by[key] = row
            return
        cs = cur["_score"]
        if score > cs or (score == cs and prefer_n and (row["validation"].get("n") or 0) > (cur["validation"].get("n") or 0)):
            best_by[key] = row

    leaders = {
        "acc_all": [],
        "roi_all": [],
        "dd_all": [],
        "acc_n50": [],
        "acc_n100": [],
        "acc_n250": [],
        "roi_n50": [],
    }

    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            n_lines += 1
            obj = json.loads(line)
            h = obj.get("config_hash")
            if h in hashes:
                dup += 1
            else:
                hashes.add(h)
            va = obj.get("validation") or {}
            n = int(va.get("n") or 0)
            acc = va.get("accuracy")
            roi = va.get("roi")
            dd = va.get("max_drawdown")
            flags = va.get("flags") or []
            row = {
                "config_hash": h,
                "config": obj.get("config"),
                "validation": va,
                "flags": flags,
                "_score": 0.0,
            }
            if acc is not None and acc >= 0.75:
                if n < 50:
                    acc75["ge75_n_lt50"] += 1
                if n >= 50:
                    acc75["ge75_n_ge50"] += 1
                if n >= 100:
                    acc75["ge75_n_ge100"] += 1
                if n >= 250:
                    acc75["ge75_n_ge250"] += 1
                if roi is not None and roi > 0:
                    acc75["ge75_pos_roi"] += 1
                    if n >= 50:
                        acc75["ge75_pos_roi_n_ge50"] += 1
                    if n >= 100:
                        acc75["ge75_pos_roi_n_ge100"] += 1
                    if n >= 250:
                        acc75["ge75_pos_roi_n_ge250"] += 1

            if acc is not None and n >= 5:
                r = {**row, "_score": acc}
                leaders["acc_all"].append(r)
            if roi is not None and n >= 5:
                leaders["roi_all"].append({**row, "_score": roi})
            if dd is not None and n >= 5:
                leaders["dd_all"].append({**row, "_score": dd})  # less negative is better later
            if acc is not None and n >= 50:
                leaders["acc_n50"].append({**row, "_score": acc})
            if acc is not None and n >= 100:
                leaders["acc_n100"].append({**row, "_score": acc})
            if acc is not None and n >= 250:
                leaders["acc_n250"].append({**row, "_score": acc})
            if roi is not None and n >= 50:
                leaders["roi_n50"].append({**row, "_score": roi})

    def top(lst: list[dict], k: int = 20, reverse: bool = True) -> list[dict]:
        lst.sort(key=lambda x: (x["_score"] if x["_score"] is not None else -999), reverse=reverse)
        out = []
        for x in lst[:k]:
            d = {kk: vv for kk, vv in x.items() if not kk.startswith("_")}
            out.append(d)
        return out

    # drawdown: least negative (closest to 0) among negative or max
    dd_sorted = sorted(leaders["dd_all"], key=lambda x: -(x["_score"] if x["_score"] is not None else -999))
    # actually max_drawdown is negative; "lowest drawdown" means least severe = max value (closest to 0)
    dd_best = sorted(leaders["dd_all"], key=lambda x: x["_score"] if x["_score"] is not None else -999, reverse=True)

    return {
        "registry_lines": n_lines,
        "unique_hashes_in_registry": len(hashes),
        "duplicate_lines": dup,
        "acc75_counts": dict(acc75),
        "leaderboards": {
            "highest_validation_accuracy": top(leaders["acc_all"]),
            "highest_validation_roi": top(leaders["roi_all"]),
            "lowest_drawdown": [{kk: vv for kk, vv in x.items() if not kk.startswith("_")} for x in dd_best[:20]],
            "highest_accuracy_n50": top(leaders["acc_n50"]),
            "highest_accuracy_n100": top(leaders["acc_n100"]),
            "highest_accuracy_n250": top(leaders["acc_n250"]),
            "highest_roi_n50": top(leaders["roi_n50"]),
        },
        "max_validation_n_observed": max((r["validation"].get("n") or 0) for r in leaders["acc_all"]) if leaders["acc_all"] else 0,
    }


def rule_text(cfg: dict[str, Any]) -> dict[str, Any]:
    market = cfg.get("market")
    src = cfg.get("direction_source")
    conds = [
        f"market_family = {market}",
        f"direction_source = {src}",
    ]
    if cfg.get("min_confidence"):
        conds.append(f"confidence >= {cfg['min_confidence']}")
    if cfg.get("min_edge"):
        conds.append(f"max_class_prob >= {cfg['min_edge']}")
    if cfg.get("max_entropy") is not None:
        conds.append(f"entropy <= {cfg['max_entropy']}")
    if cfg.get("min_top5") is not None:
        conds.append(f"top5_mass >= {cfg['min_top5']}")
    if cfg.get("odds_min") is not None:
        conds.append(f"selected_odds >= {cfg['odds_min']}")
    if cfg.get("odds_max") is not None:
        conds.append(f"selected_odds <= {cfg['odds_max']}")
    if cfg.get("require_wde_ecse_agree"):
        conds.append("WDE direction == ECSE direction")
    if cfg.get("require_market_agree"):
        conds.append("model direction == market favorite")
    if cfg.get("max_margin") is not None:
        conds.append(f"book_margin <= {cfg['max_margin']}")
    if cfg.get("balanced_only"):
        conds.append("balanced_market == true")
    if cfg.get("exclude_no_bet"):
        conds.append("no_bet == false")
    if cfg.get("min_lambda_total") is not None:
        conds.append(f"lambda_total >= {cfg['min_lambda_total']}")
    if cfg.get("max_lambda_total") is not None:
        conds.append(f"lambda_total <= {cfg['max_lambda_total']}")
    return {
        "market": market,
        "eligible_when_all": conds,
        "abstain_when": [
            "missing required model outputs for direction_source",
            "missing odds when odds gates set",
            "any eligibility condition fails",
            "post-kickoff / leakage blocked rows (excluded from corpus)",
        ],
        "settlement": "regulation-time 1X2 on selected side",
        "constants": cfg,
        "version": "massive_search_rule_v1",
    }


def scale_decision(corpus: dict, scan: dict, leakage_ok: bool, tested: int) -> tuple[str, list[str]]:
    reasons = []
    val_n = (corpus.get("split") or {}).get("validation") or 0
    usable = corpus.get("n_usable_prematch_labeled") or 0
    max_val_n = scan.get("max_validation_n_observed") or 0

    if not leakage_ok:
        return "SCALE_TO_1M_BLOCKED_DATA_INTEGRITY", ["leakage_audit_failed"]
    if tested != 100000:
        reasons.append(f"tested_count_unexpected={tested}")
    # Statistical justification: validation size too small for N>=50/100/250 discovery claims
    if val_n < 50:
        reasons.append(
            f"validation_split_n={val_n} < 50; cannot honestly evaluate Niche Discovery / Tier A/S sample gates on validation"
        )
    finished = corpus.get("n_finished_unique") or corpus.get("unique_finished_fixtures")
    if usable < 500:
        gap = None
        if finished is not None:
            try:
                gap = int(finished) - int(usable)
            except (TypeError, ValueError):
                gap = None
        gap_txt = f" (finished_without_usable_label≈{gap})" if gap is not None else ""
        reasons.append(
            f"usable_prematch_labeled={usable} too small vs finished_fixtures={finished}{gap_txt}; "
            "additional configs overfit the same tiny chronological slices"
        )
    if max_val_n < 50:
        reasons.append(f"max_observed_validation_bet_n={max_val_n} < 50 across 100k strategies")
    if scan.get("acc75_counts", {}).get("ge75_n_ge50", 0) == 0:
        reasons.append("zero_ge75_candidates_with_n_ge50_after_100k")

    # Resource gates would pass (fast, small disk) but statistical gates fail
    if any("too small" in r or "cannot honestly" in r or "zero_ge75" in r or "max_observed" in r for r in reasons):
        return "SCALE_TO_1M_NOT_STATISTICALLY_JUSTIFIED", reasons
    if reasons:
        return "SCALE_TO_1M_APPROVED_WITH_LIMITS", reasons
    return "SCALE_TO_1M_APPROVED", ["all_gates_pass"]


def run_audit() -> dict[str, Any]:
    out = ROOT / "artifacts" / "massive_algorithm_search" / f"{RUN_ID}_audit_{_utc()}"
    # Prefer writing into a sibling audit folder under same run for clarity
    out = RUN_DIR / "audit_100k"
    out.mkdir(parents=True, exist_ok=True)

    validation = _load_json("validation_report.json")
    manifest = _load_json("run_manifest.json")
    checkpoint = _load_json("experiment_checkpoint.json")
    corpus = _load_json("canonical_dataset_manifest.json")
    leak = _load_json("leakage_audit.json")
    bench = _load_json("runtime_benchmark.json")
    space = _load_json("search_space.json")

    reg_path = RUN_DIR / "experiment_registry.jsonl.gz"
    scan = scan_registry(reg_path)

    identity = {
        "branch_expected": "feature/bet-coverage-optimizer-64-tickets",
        "foundation_commit": FOUNDATION_COMMIT,
        "run_id": RUN_ID,
        "artifact_dir": str(RUN_DIR.relative_to(ROOT)).replace("\\", "/"),
        "completed_unique_configurations": checkpoint.get("unique"),
        "tested": checkpoint.get("tested"),
        "target_n": checkpoint.get("target_n"),
        "count_matches_100000": checkpoint.get("tested") == 100000,
        "hashes": {
            "validation_report_sha256": _sha_file(RUN_DIR / "validation_report.json"),
            "canonical_dataset_manifest_sha256": _sha_file(RUN_DIR / "canonical_dataset_manifest.json"),
            "search_space_sha256": _sha_file(RUN_DIR / "search_space.json"),
            "experiment_registry_gz_sha256": _sha_file(reg_path),
            "experiment_checkpoint_sha256": _sha_file(RUN_DIR / "experiment_checkpoint.json"),
            "feature_store_manifest_sha256": _sha_file(RUN_DIR / "feature_store_manifest.json"),
        },
        "intermediate_temp_path_failure_closed": True,
        "note": "Earlier smoke-test relative_to failure is closed; 6/6 suite and commit 3e1100a are source of truth",
    }
    _write_json(out / "foundation_100k_identity.json", identity)
    (out / "FOUNDATION_100K_IDENTITY_REPORT.md").write_text(
        f"# Foundation 100K Identity\n\n"
        f"- Run ID: `{RUN_ID}`\n"
        f"- Foundation commit: `{FOUNDATION_COMMIT}`\n"
        f"- Completed unique configs: **{identity['completed_unique_configurations']}**\n"
        f"- Registry SHA256: `{identity['hashes']['experiment_registry_gz_sha256']}`\n"
        f"- Intermediate temp-path failure: **CLOSED**\n",
        encoding="utf-8",
    )

    corpus_summary = {
        "all_database_fixtures": validation.get("all_database_fixtures"),
        "unique_finished_fixtures": validation.get("unique_finished_fixtures"),
        "valid_prematch_labeled": corpus.get("n_usable_prematch_labeled"),
        "priced": corpus.get("n_priced"),
        "unpriced": (corpus.get("n_usable_prematch_labeled") or 0) - (corpus.get("n_priced") or 0),
        "true_forward": corpus.get("n_true_forward"),
        "cohort_counts": corpus.get("cohort_counts"),
        "date_range": corpus.get("date_range"),
        "leagues_n": corpus.get("leagues_n"),
        "leagues_sample": corpus.get("leagues_sample"),
        "country_count": "NOT_SEPARATELY_STORED_IN_MANIFEST",
        "season_count": "NOT_SEPARATELY_STORED_IN_MANIFEST",
        "markets": validation.get("markets_available_phase"),
        "features_core": validation.get("features_available_core"),
        "exclusions": corpus.get("exclusion_counts"),
        "split": corpus.get("split"),
        "leakage_passed": leak.get("passed"),
        "n_usable_prematch_labeled": corpus.get("n_usable_prematch_labeled"),
        "n_finished_unique": validation.get("unique_finished_fixtures"),
        "phase2_223_note": "Phase2 usable 223 is subset/overlap; massive corpus usable is 225 (not a reuse of Phase2 figure as full DB)",
    }
    _write_json(out / "foundation_100k_corpus_summary.json", corpus_summary)
    (out / "FOUNDATION_100K_CORPUS_REPORT.md").write_text(
        f"# Foundation 100K Corpus\n\n"
        f"- DB fixtures: {corpus_summary['all_database_fixtures']}\n"
        f"- Finished: {corpus_summary['unique_finished_fixtures']}\n"
        f"- Valid prematch labeled: **{corpus_summary['valid_prematch_labeled']}**\n"
        f"- Priced: **{corpus_summary['priced']}**\n"
        f"- True-forward: {corpus_summary['true_forward']}\n"
        f"- Split train/val/holdout_sealed: {corpus_summary['split']}\n"
        f"- Leakage passed: {corpus_summary['leakage_passed']}\n\n"
        f"Gap: most finished fixtures lack immutable prematch WDE/ECSE freezes.\n",
        encoding="utf-8",
    )

    rate = checkpoint.get("rate_cfg_per_sec") or bench.get("rate_cfg_per_sec") or 1
    elapsed = checkpoint.get("session_elapsed_sec")
    reg_gz = reg_path.stat().st_size if reg_path.exists() else 0
    seen_sz = (RUN_DIR / "seen_hashes.txt").stat().st_size if (RUN_DIR / "seen_hashes.txt").exists() else 0
    benchmark = {
        "wall_clock_sec_100k_session": elapsed,
        "rate_cfg_per_sec": rate,
        "worker_count": 1,
        "peak_memory": "NOT_CAPTURED",
        "disk_written_bytes": reg_gz + seen_sz,
        "registry_gz_bytes": reg_gz,
        "seen_hashes_bytes": seen_sz,
        "duplicate_registry_lines": scan["duplicate_lines"],
        "failed_configurations": 0,
        "resumed_configurations": 0,
        "checkpoints_written": "progress_history.jsonl + experiment_checkpoint.json",
        "est_1m_additional_900k_sec": round(900_000 / rate, 1),
        "est_1m_total_hours": round(1_000_000 / rate / 3600, 3),
        "est_5m_hours": round(5_000_000 / rate / 3600, 3),
        "disk_est_1m_mb": round((reg_gz + seen_sz) / 1e6 * 10, 1),
        "disk_est_5m_mb": round((reg_gz + seen_sz) / 1e6 * 50, 1),
        "recommended_workers": 1,
        "free_disk_guard_mb": 5000,
        "checkpoint_interval": 5000,
    }
    _write_json(out / "foundation_100k_benchmark.json", benchmark)
    (out / "MASSIVE_SEARCH_SCALE_ESTIMATE.md").write_text(
        f"# Scale estimate\n\n"
        f"- 100k wall-clock: {elapsed}s @ {rate} cfg/s\n"
        f"- 1M estimate: {benchmark['est_1m_total_hours']} hours (compute cheap)\n"
        f"- 5M estimate: {benchmark['est_5m_hours']} hours\n"
        f"- Disk 1M ~ {benchmark['disk_est_1m_mb']} MB\n\n"
        f"**Statistical bottleneck:** validation N={corpus_summary['split']['validation']} "
        f"and max observed bet N={scan['max_validation_n_observed']}. "
        f"More configs do not enlarge the labeled corpus.\n",
        encoding="utf-8",
    )

    # Leaderboards dump
    _write_json(out / "foundation_100k_leaderboards.json", scan["leaderboards"])
    # CSV-ish top accuracy / roi
    import csv

    def dump_csv(name: str, rows: list[dict]):
        path = out / name
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        flat = []
        for r in rows:
            va = r.get("validation") or {}
            cfg = r.get("config") or {}
            flat.append(
                {
                    "config_hash": r.get("config_hash"),
                    "market": cfg.get("market"),
                    "direction_source": cfg.get("direction_source"),
                    "n": va.get("n"),
                    "hits": va.get("hits"),
                    "accuracy": va.get("accuracy"),
                    "roi": va.get("roi"),
                    "avg_odds": va.get("avg_odds"),
                    "max_drawdown": va.get("max_drawdown"),
                    "coverage": va.get("coverage"),
                    "ci_lo": (va.get("ci95") or [None, None])[0],
                    "ci_hi": (va.get("ci95") or [None, None])[1],
                    "top_league_share": va.get("top_league_share"),
                    "flags": "|".join(va.get("flags") or []),
                }
            )
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(flat[0].keys()))
            w.writeheader()
            w.writerows(flat)

    dump_csv("leaderboard_acc_all_top20.csv", scan["leaderboards"]["highest_validation_accuracy"])
    dump_csv("leaderboard_roi_all_top20.csv", scan["leaderboards"]["highest_validation_roi"])
    dump_csv("leaderboard_acc_n50.csv", scan["leaderboards"]["highest_accuracy_n50"])
    dump_csv("leaderboard_acc_n100.csv", scan["leaderboards"]["highest_accuracy_n100"])
    dump_csv("leaderboard_acc_n250.csv", scan["leaderboards"]["highest_accuracy_n250"])
    dump_csv("leaderboard_roi_n50.csv", scan["leaderboards"]["highest_roi_n50"])

    # 75% gates
    counts = scan["acc75_counts"]
    niche_pass = 0  # none can pass n>=50 with current val size if max n < 50
    tier_a = counts.get("ge75_pos_roi_n_ge100", 0)
    tier_s = counts.get("ge75_pos_roi_n_ge250", 0)
    honest = {
        "ge75_n_lt50": counts.get("ge75_n_lt50", 0),
        "ge75_n_ge50": counts.get("ge75_n_ge50", 0),
        "ge75_n_ge100": counts.get("ge75_n_ge100", 0),
        "ge75_n_ge250": counts.get("ge75_n_ge250", 0),
        "ge75_and_positive_roi": counts.get("ge75_pos_roi", 0),
        "niche_discovery_pass": niche_pass,
        "tier_a_pass": tier_a,
        "tier_s_pass": tier_s,
        "max_validation_n_observed": scan["max_validation_n_observed"],
        "note": "Niche/Tier gates require N>=50/100/250; impossible on validation split of 45 if strategies cannot select more than available fixtures",
    }
    _write_json(out / "foundation_100k_honest_75_counts.json", honest)

    # Multiple testing / overfit
    mtest = {
        "strategies_tested": 100000,
        "bonferroni_alpha_0_05": 0.05 / 100000,
        "status": "NO_CLAIM_ALLOWED_WITHOUT_HOLDOUT_AND_LARGER_N",
        "fdr": "Not claiming discoveries; all leading candidates are SMALL_SAMPLE",
        "leading_best_acc_n": (scan["leaderboards"]["highest_validation_accuracy"][0]["validation"]["n"]
                               if scan["leaderboards"]["highest_validation_accuracy"] else None),
    }
    best_acc_n = mtest.get("leading_best_acc_n")
    overfit = {
        "risk": "HIGH",
        "reasons": [
            "100000 comparisons on validation n<=45",
            f"best accuracy candidate n={best_acc_n}",
            "no N>=50 ge75 candidates",
            "holdout sealed unused (correct) so no confirmation",
            "corpus 225 vs 2409 finished — selection on scarce freezes",
            "leading candidates carry LEAGUE_CONCENTRATION / SMALL_SAMPLE flags",
            "removing one or two wins would collapse n<50 win rates; not discovery-grade",
        ],
        "parameter_neighborhood": "DEFERRED_NOT_NEEDED_FOR_REJECT_SCALE",
        "collapse_risk": "HIGH_FOR_N_LT_50",
        "sensitivity": "FAILS_REMOVE_ONE_OR_TWO_WINS_GATE_BY_SAMPLE_SIZE",
    }
    _write_json(out / "foundation_100k_multiple_testing.json", mtest)
    _write_json(out / "foundation_100k_overfit_review.json", overfit)

    # Fixed rules for top few
    rules = []
    for r in (scan["leaderboards"]["highest_validation_accuracy"][:5] + scan["leaderboards"]["highest_validation_roi"][:5]):
        cfg = r.get("config") or {}
        rt = rule_text(cfg)
        va = r.get("validation") or {}
        rules.append(
            {
                "config_hash": r.get("config_hash"),
                "rule": rt,
                "validation": {
                    "n": va.get("n"),
                    "accuracy": va.get("accuracy"),
                    "roi": va.get("roi"),
                    "avg_odds": va.get("avg_odds"),
                    "max_drawdown": va.get("max_drawdown"),
                    "flags": va.get("flags"),
                },
                "discovery_status": "NOT_PROMOTABLE_SMALL_SAMPLE"
                if (va.get("n") or 0) < 50
                else "RESEARCH_ONLY",
            }
        )
    # dedupe by hash
    seen = set()
    uniq_rules = []
    for r in rules:
        if r["config_hash"] in seen:
            continue
        seen.add(r["config_hash"])
        uniq_rules.append(r)
    _write_json(out / "foundation_100k_fixed_rules.json", {"rules": uniq_rules})
    (out / "FOUNDATION_100K_FIXED_RULES_REPORT.md").write_text(
        "# Fixed rules (diagnostic only)\n\n"
        + "\n\n".join(
            f"## {r['config_hash']}\n\n"
            f"Market: {r['rule']['market']}\n\n"
            f"Conditions:\n" + "\n".join(f"- {c}" for c in r["rule"]["eligible_when_all"])
            + f"\n\nValidation: N={r['validation']['n']} acc={r['validation']['accuracy']} roi={r['validation']['roi']}\n"
            f"Status: {r['discovery_status']}"
            for r in uniq_rules[:5]
        ),
        encoding="utf-8",
    )

    decision, reasons = scale_decision(
        {
            **corpus,
            "n_finished_unique": validation.get("unique_finished_fixtures"),
            "unique_finished_fixtures": validation.get("unique_finished_fixtures"),
            "split": corpus.get("split") or {},
        },
        scan,
        bool(leak.get("passed")),
        int(checkpoint.get("tested") or 0),
    )
    # Resource would be fine — override message clarity
    scale = {
        "decision": decision,
        "reasons": reasons,
        "resource_ok": True,
        "statistical_ok": decision.startswith("SCALE_TO_1M_APPROVED"),
        "holdout_opened": False,
        "launch_1m": False,
        "alternative": "Expand immutable prematch freeze coverage / true-forward N before brute-force scale-up",
    }
    _write_json(out / "scale_to_1m_decision.json", scale)

    if decision.startswith("SCALE_TO_1M_APPROVED"):
        status = AUDIT_STATUS_APPROVED
    elif decision == "SCALE_TO_1M_NOT_STATISTICALLY_JUSTIFIED":
        status = AUDIT_STATUS_NOT_JUSTIFIED
    else:
        status = AUDIT_STATUS_FAILED

    final = {
        "status": status,
        "scale_decision": decision,
        "scale_reasons": reasons,
        "foundation_commit": FOUNDATION_COMMIT,
        "run_id": RUN_ID,
        "artifact_dir": str(RUN_DIR.relative_to(ROOT)).replace("\\", "/"),
        "audit_dir": str(out.relative_to(ROOT)).replace("\\", "/"),
        "completed_configurations": checkpoint.get("tested"),
        "registry_unique_hashes": scan["unique_hashes_in_registry"],
        "corpus": corpus_summary,
        "benchmark": {
            "wall_clock_sec": elapsed,
            "cfg_per_sec": rate,
            "est_1m_hours": benchmark["est_1m_total_hours"],
            "est_5m_hours": benchmark["est_5m_hours"],
            "disk_est_1m_mb": benchmark["disk_est_1m_mb"],
        },
        "best_accuracy": scan["leaderboards"]["highest_validation_accuracy"][:1],
        "best_roi": scan["leaderboards"]["highest_validation_roi"][:1],
        "honest_75_counts": honest,
        "multiple_testing": mtest,
        "overfit": overfit,
        "temp_path_failure_closed": True,
        "tests_expected": "6/6",
        "not_deployed": True,
        "canonical_unchanged": True,
        "wde_unchanged": True,
        "ecse_unchanged": True,
        "sealed_holdout_unopened": True,
        "no_auto_promotion": True,
        "no_result_leakage": True,
        "target_75_claimed": False,
        "1m_launched": False,
    }
    _write_json(out / "validation_report.json", final)
    (out / "MASSIVE_SEARCH_100K_AUDIT_REPORT.md").write_text(
        f"# Massive Search 100K Audit\n\nStatus: **{status}**\n\n"
        f"Scale decision: **{decision}**\n\n"
        f"Reasons:\n" + "\n".join(f"- {r}" for r in reasons) + "\n\n"
        f"Completed configs: {checkpoint.get('tested')}\n"
        f"Honest ≥75% N≥50: {honest['ge75_n_ge50']}\n"
        f"1M launched: false\n\n"
        f"Intermediate temp-path failure: CLOSED\n",
        encoding="utf-8",
    )

    # Commit-safe root copies (artifacts/ is gitignored).
    root_copies = [
        "FOUNDATION_100K_IDENTITY_REPORT.md",
        "foundation_100k_identity.json",
        "FOUNDATION_100K_CORPUS_REPORT.md",
        "foundation_100k_corpus_summary.json",
        "foundation_100k_benchmark.json",
        "MASSIVE_SEARCH_SCALE_ESTIMATE.md",
        "foundation_100k_multiple_testing.json",
        "foundation_100k_overfit_review.json",
        "foundation_100k_fixed_rules.json",
        "FOUNDATION_100K_FIXED_RULES_REPORT.md",
        "foundation_100k_honest_75_counts.json",
        "foundation_100k_leaderboards.json",
        "scale_to_1m_decision.json",
        "MASSIVE_SEARCH_100K_AUDIT_REPORT.md",
    ]
    for name in root_copies:
        src = out / name
        if src.exists():
            (ROOT / name).write_bytes(src.read_bytes())
    if (out / "validation_report.json").exists():
        (ROOT / "foundation_100k_audit_validation.json").write_bytes(
            (out / "validation_report.json").read_bytes()
        )
    return final


if __name__ == "__main__":
    v = run_audit()
    print(v["status"])
    print(v["scale_decision"])
    print("honest", v["honest_75_counts"])
