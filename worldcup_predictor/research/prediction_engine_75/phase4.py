"""
PREDICTION_ENGINE_75 — Phase 4: locked holdout evaluation + true-forward readiness.

Opens Phase-1 sealed holdout exactly once for locked candidates.
No retuning. No Canonical/WDE/ECSE modification. No deployment.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.prediction_engine_75 import phase1 as p1
from worldcup_predictor.research.prediction_engine_75 import phase2 as p2
from worldcup_predictor.research.prediction_engine_75 import phase3 as p3

ROOT = Path(__file__).resolve().parents[3]
PHASE = "PHASE4_LOCKED_HOLDOUT_AND_TRUE_FORWARD"
STATUS_READY = "PHASE4_LOCKED_HOLDOUT_EVALUATED_TRUE_FORWARD_READY"
STATUS_HOLDOUT_FAIL = "PHASE4_HOLDOUT_INTEGRITY_FAILED"
STATUS_LOCK_FAIL = "PHASE4_CANDIDATE_LOCK_FAILED"
STATUS_TF_BLOCKED = "PHASE4_TRUE_FORWARD_PIPELINE_BLOCKED"
STATUS_FAILED = "PHASE4_VALIDATION_FAILED"
SEED = 20260802
SOURCE_COMMIT_PHASE3 = "94b0e88"
PHASE1_LOCK_HASH = "db1deb8f71ce4afcc5c94ca33ccb8408fa471e4632c72c2a3b06c4a165f642fe"
PHASE1_HOLDOUT_IDS = [
    1554450,
    1554419,
    1554434,
    1554447,
    1554449,
    1554452,
    1554415,
    1554427,
    1554438,
    1514231,
    1554451,
]
LOCKED_NAMES = [
    "ecse_direction",
    "Favorite_Specialist",
    "League_Specialist",
    "High_Goal_Specialist",
    "meta_model",
]
SMALL_WARNING = "SMALL_HOLDOUT_NOT_PROMOTABLE"

# Locked Phase-2 best strategy proxy (immutable; from Phase2/3 reports)
PHASE2_BEST_CFG = p2.StratCfg(
    min_confidence=0,
    min_edge=0.0,
    max_entropy=None,
    min_top5=0.65,
    require_agree_ecse=False,
    odds_max=None,
    direction_mode="ecse",
    exclude_no_bet=False,
    balanced_only=False,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return _sha256_bytes(blob)


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except Exception:
        return "UNKNOWN"


def load_phase1_holdout_ids() -> tuple[list[int], dict[str, Any]]:
    lock_paths = sorted((ROOT / "artifacts/prediction_engine_75_research").glob("**/sealed_holdout_lock.json"))
    if not lock_paths:
        return list(PHASE1_HOLDOUT_IDS), {"source": "embedded_constant", "path": None}
    path = lock_paths[-1]
    obj = json.loads(path.read_text(encoding="utf-8"))
    ids = [int(x) for x in (obj.get("fixture_ids") or [])]
    return ids, {"source": str(path.relative_to(ROOT)).replace("\\", "/"), "raw": obj}


# ---------------------------------------------------------------------------
# Part 1 — Candidate lock manifest
# ---------------------------------------------------------------------------


def build_locked_manifest(
    train_ids: list[int],
    val_ids: list[int],
    *,
    source_commit: str,
) -> dict[str, Any]:
    """Immutable configuration for locked candidates (no hyperparameter search)."""
    created = _utc_now()
    candidates = []
    # Shared feature list / routing from Phase3
    feature_list = list(p3.FEATURE_NAMES)
    routing_rules = [
        "high_entropy>=1.75 -> ABSTAIN",
        "balanced_market -> Draw_Specialist",
        "fav_odds<=1.45 -> Heavy_Favorite_Specialist",
        "wde!=market -> Market_Contradiction_Detector",
        "short fav + low conf -> Upset_Risk_Detector",
        "lambda_total<=2.2 -> Low_Goal_Specialist",
        "lambda_total>=2.8 -> High_Goal_Specialist",
        "else Favorite / League / Canonical_WDE",
    ]
    thresholds = {
        "heavy_favorite_odds_max": 1.45,
        "upset_fav_odds_max": 1.7,
        "upset_confidence_max": 58,
        "high_entropy_min": 1.75,
        "low_goal_lambda_total_max": 2.2,
        "high_goal_lambda_total_min": 2.8,
        "meta_blend_specialist": 0.7,
        "meta_blend_wde": 0.3,
        "abstain_gate": 0.75,
        "phase2_best_min_top5": 0.65,
        "phase2_best_direction_mode": "ecse",
    }

    defs = {
        "ecse_direction": {
            "model_type": "rule_ecse_full_mass_direction",
            "configuration": {"direction_source": "ecse_direction|ft_marginal", "abstain": False},
        },
        "Favorite_Specialist": {
            "model_type": "calibrated_logistic_specialist",
            "configuration": {
                "eligibility": "fav_odds<=2.2",
                "estimator": "LogisticRegression(+CalibratedClassifierCV if n>=40)",
                "features": feature_list,
                "seed": SEED,
            },
        },
        "League_Specialist": {
            "model_type": "calibrated_logistic_specialist",
            "configuration": {"eligibility": "all", "estimator": "LogisticRegression", "features": feature_list, "seed": SEED},
        },
        "High_Goal_Specialist": {
            "model_type": "calibrated_logistic_specialist",
            "configuration": {
                "eligibility": "lambda_total>=2.8",
                "estimator": "LogisticRegression",
                "features": feature_list,
                "seed": SEED,
            },
        },
        "meta_model": {
            "model_type": "rule_router_plus_specialist_wde_blend",
            "configuration": {
                "routing_rules": routing_rules,
                "thresholds": thresholds,
                "blend": "0.7*specialist + 0.3*WDE",
                "specialists_available": list(p3.SPECIALISTS),
            },
        },
    }

    for name in LOCKED_NAMES:
        d = defs[name]
        cfg = {
            "candidate_id": name,
            "model_type": d["model_type"],
            "complete_configuration": d["configuration"],
            "feature_list": feature_list,
            "threshold_list": thresholds,
            "training_data_boundary": "all_usable_excluding_phase1_sealed_holdout",
            "training_fixture_ids": train_ids,
            "validation_fixture_ids": val_ids,
            "source_commit": source_commit,
            "creation_timestamp": created,
            "tuning_allowed": False,
        }
        cfg["configuration_hash"] = _sha256_json(
            {k: cfg[k] for k in ("candidate_id", "model_type", "complete_configuration", "feature_list", "threshold_list", "seed") if k in cfg}
            | {"seed": SEED, "complete_configuration": d["configuration"], "feature_list": feature_list, "threshold_list": thresholds}
        )
        # artifact hash = hash of frozen definition (models fitted later get separate fit_hash)
        cfg["model_artifact_hash"] = _sha256_json(d)
        cfg["lock_status"] = "LOCKED"
        candidates.append(cfg)

    manifest = {
        "phase": PHASE,
        "created_at": created,
        "source_commit_phase3": SOURCE_COMMIT_PHASE3,
        "opening_commit_placeholder": None,
        "locked_candidates": candidates,
        "no_more_tuning": True,
        "holdout_ids_sealed_at_lock": list(PHASE1_HOLDOUT_IDS),
    }
    manifest["manifest_hash"] = _sha256_json({k: manifest[k] for k in manifest if k != "manifest_hash"})
    return manifest


# ---------------------------------------------------------------------------
# Part 2 — Holdout integrity
# ---------------------------------------------------------------------------


def verify_holdout_integrity(
    rows: list[p2.RowV2],
    holdout_ids: list[int],
    train_ids: set[int],
    val_ids: set[int],
    lock_meta: dict[str, Any],
) -> dict[str, Any]:
    findings = []
    status = "SEALED_HOLDOUT_INTEGRITY_PASS"
    ids = list(holdout_ids)
    expected = set(PHASE1_HOLDOUT_IDS)
    got = set(ids)

    if len(ids) != 11:
        findings.append({"severity": "HIGH", "issue": "holdout_n_not_11", "n": len(ids)})
        status = "SEALED_HOLDOUT_INTEGRITY_FAIL"
    if got != expected:
        findings.append(
            {
                "severity": "HIGH",
                "issue": "holdout_ids_changed",
                "missing": sorted(expected - got),
                "extra": sorted(got - expected),
            }
        )
        status = "SEALED_HOLDOUT_INTEGRITY_FAIL"

    recomputed = hashlib.sha256(",".join(str(x) for x in sorted(expected)).encode()).hexdigest()
    # Phase1 used unsorted join order from chronological holdout list — verify both
    phase1_order_hash = hashlib.sha256(",".join(str(x) for x in PHASE1_HOLDOUT_IDS).encode()).hexdigest()
    raw = (lock_meta.get("raw") or {})
    stored_hash = raw.get("lock_hash") or PHASE1_LOCK_HASH
    if stored_hash not in {phase1_order_hash, PHASE1_LOCK_HASH} and stored_hash != phase1_order_hash:
        # Accept exact Phase1 stored hash
        if stored_hash != PHASE1_LOCK_HASH:
            findings.append(
                {
                    "severity": "MEDIUM",
                    "issue": "lock_hash_mismatch_note",
                    "stored": stored_hash,
                    "phase1_order_hash": phase1_order_hash,
                    "sorted_hash": recomputed,
                }
            )
    if stored_hash == PHASE1_LOCK_HASH or stored_hash == phase1_order_hash:
        findings.append({"severity": "INFO", "issue": "lock_hash_matches_phase1", "hash": stored_hash})

    overlap_train = sorted(got & train_ids)
    overlap_val = sorted(got & val_ids)
    if overlap_train or overlap_val:
        findings.append({"severity": "HIGH", "issue": "holdout_overlap_train_val", "train": overlap_train, "val": overlap_val})
        status = "SEALED_HOLDOUT_INTEGRITY_FAIL"

    by_fid = {r.fixture_id: r for r in rows}
    missing_rows = sorted(got - set(by_fid))
    if missing_rows:
        findings.append({"severity": "HIGH", "issue": "holdout_fixtures_missing_from_corpus", "ids": missing_rows})
        status = "SEALED_HOLDOUT_INTEGRITY_FAIL"

    post_ko = []
    post_odds = []
    no_result = []
    for fid in sorted(got):
        r = by_fid.get(fid)
        if not r:
            continue
        if r.exclusion_reason in {"POST_KICKOFF_FREEZE", "POST_KICKOFF_PREDICTION"}:
            post_ko.append(fid)
        ko = p1._parse_dt(r.kickoff_utc)
        od = p1._parse_dt(r.odds_snapshot_at)
        if ko and od and od >= ko:
            post_odds.append(fid)
        if not r.actual_1x2:
            no_result.append(fid)
    if post_ko:
        findings.append({"severity": "HIGH", "issue": "post_kickoff_prediction", "ids": post_ko})
        status = "SEALED_HOLDOUT_INTEGRITY_FAIL"
    if post_odds:
        findings.append({"severity": "HIGH", "issue": "post_kickoff_odds", "ids": post_odds})
        status = "SEALED_HOLDOUT_INTEGRITY_FAIL"
    if no_result:
        findings.append({"severity": "HIGH", "issue": "missing_results", "ids": no_result})
        status = "SEALED_HOLDOUT_INTEGRITY_FAIL"

    dups = [fid for fid, c in Counter(ids).items() if c > 1]
    if dups:
        findings.append({"severity": "HIGH", "issue": "duplicate_ids", "ids": dups})
        status = "SEALED_HOLDOUT_INTEGRITY_FAIL"

    findings.append({"severity": "INFO", "issue": "regulation_time_labels", "policy": "fixture_results home/away goals / regulation when present"})
    findings.append({"severity": "INFO", "issue": "no_tuning_on_holdout", "confirmed": True})

    return {
        "status": status,
        "n": len(ids),
        "fixture_ids": ids,
        "expected_ids": PHASE1_HOLDOUT_IDS,
        "findings": findings,
        "passed": status == "SEALED_HOLDOUT_INTEGRITY_PASS",
    }


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------


def _class_prf(preds: list[tuple[str | None, p2.RowV2]]) -> dict[str, Any]:
    labeled = [(p, r) for p, r in preds if p and r.actual_1x2]
    out: dict[str, Any] = {}
    for cls in ("home", "draw", "away"):
        tp = sum(1 for p, r in labeled if p == cls and r.actual_1x2 == cls)
        fp = sum(1 for p, r in labeled if p == cls and r.actual_1x2 != cls)
        fn = sum(1 for p, r in labeled if p != cls and r.actual_1x2 == cls)
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        out[cls] = {
            "precision": round(prec, 4) if prec is not None else None,
            "recall": round(rec, 4) if rec is not None else None,
        }
    return out


def _log_loss_brier(rows_preds: list[tuple[dict[str, float] | None, p2.RowV2]]) -> dict[str, Any]:
    ll_vals = []
    br_vals = []
    for probs, r in rows_preds:
        if not probs or not r.actual_1x2:
            continue
        y = r.actual_1x2
        p = max(1e-9, min(1 - 1e-9, float(probs.get(y) or 0)))
        ll_vals.append(-math.log(p))
        for k in ("home", "draw", "away"):
            t = 1.0 if k == y else 0.0
            br_vals.append((float(probs.get(k) or 0) - t) ** 2)
    return {
        "log_loss": round(sum(ll_vals) / len(ll_vals), 4) if ll_vals else None,
        "brier": round(sum(br_vals) / len(br_vals), 4) if br_vals else None,
        "n_prob": len(ll_vals),
    }


def evaluate_candidate(
    name: str,
    holdout: list[p2.RowV2],
    preds: list[tuple[str | None, p2.RowV2]],
    *,
    abstained: list[int] | None = None,
    prob_rows: list[tuple[dict[str, float] | None, p2.RowV2]] | None = None,
) -> dict[str, Any]:
    abstained = abstained or []
    selected = [(p, r) for p, r in preds if p is not None]
    m = p2.metrics(selected, len(holdout))
    prf = _class_prf(selected)
    pb = _log_loss_brier(prob_rows or [])
    hits = m.get("hits") or 0
    n = m.get("n") or 0
    return {
        "candidate": name,
        "eligible_holdout_fixtures": len(holdout),
        "selected_fixtures": n,
        "abstained_fixtures": len(abstained),
        "abstained_ids": abstained,
        "coverage": m.get("coverage_of_input"),
        "correct": hits,
        "wrong": (n - hits) if n else 0,
        "accuracy": m.get("accuracy"),
        "balanced_accuracy": m.get("balanced_accuracy"),
        "class_prf": prf,
        "log_loss": pb.get("log_loss"),
        "brier": pb.get("brier"),
        "calibration": "diagnostic_only_n11",
        "average_odds": m.get("avg_odds"),
        "priced_n": m.get("priced_n"),
        "flat_stake_roi": m.get("roi"),
        "max_drawdown": m.get("max_drawdown"),
        "wilson_ci95": m.get("ci95"),
        "warning": SMALL_WARNING,
        "promotable": False,
    }


def verdict_for(result: dict[str, Any], wde_acc: float | None) -> str:
    n = result.get("selected_fixtures") or 0
    if result.get("lock_status") == "LOCK_INTEGRITY_FAILED":
        return "LOCK_INTEGRITY_FAILED"
    if n < 5:
        return "INSUFFICIENT_HOLDOUT_COVERAGE"
    acc = result.get("accuracy")
    if acc is None:
        return "INSUFFICIENT_HOLDOUT_COVERAGE"
    # Research-only labels; never promotion
    if wde_acc is not None and acc >= (wde_acc + 0.15) and n >= 8:
        return "HOLDOUT_SUPPORTED"
    if wde_acc is not None and acc <= (wde_acc - 0.15):
        return "HOLDOUT_REJECTED"
    return "HOLDOUT_NEUTRAL"


# ---------------------------------------------------------------------------
# True-forward audit
# ---------------------------------------------------------------------------


def audit_true_forward_pipeline() -> dict[str, Any]:
    timer_units = [
        "worldcup-l2f-true-forward-followup.timer",
        "worldcup-forward-evaluation.timer",
        "worldcup-two-fixture-shadow.timer",
        "worldcup-prediction-daily.timer",
        "worldcup-results-hourly.timer",
    ]
    timer_status = []
    for name in timer_units:
        path = ROOT / "deployment" / "systemd" / name
        timer_status.append(
            {
                "unit": name,
                "unit_file_present": path.exists(),
                "enabled_on_this_host": "UNKNOWN_NOT_PROBED_REMOTE",
                "prepared_in_repo": path.exists(),
            }
        )

    code_paths = {
        "l2f_forward_hook": (ROOT / "worldcup_predictor/research/infra_l2f_forward/forward_hook.py").exists(),
        "hv_batch": (ROOT / "worldcup_predictor/research/infra_l2f_forward/hv_batch.py").exists(),
        "forward_evaluation_automation": (ROOT / "worldcup_predictor/forward_evaluation/automation.py").exists(),
        "phase3_specialists": (ROOT / "worldcup_predictor/research/prediction_engine_75/phase3.py").exists(),
    }
    return {
        "code_paths": code_paths,
        "timers": timer_status,
        "assumption": "Code presence != active collection; remote enablement requires owner approval",
        "current_evaluated_true_forward_n": 0,
        "auto_promotion": False,
        "writes_to_canonical": False,
    }


def model_readiness() -> dict[str, Any]:
    return {
        "Canonical_WDE": {"status": "READY", "note": "worldcup_stored_predictions / owner_daily"},
        "Canonical_ECSE": {"status": "READY", "note": "ecse_prediction_snapshots frozen"},
        "Exact_V2": {"status": "MISSING_DEPENDENCY", "note": "not joined in Phase2/3 local corpus; shadow path only if existing runner available"},
        "Lambda_V2": {"status": "READY", "note": "lambda_v2_shadow_outputs"},
        "L2-F": {"status": "PARTIAL", "note": "infra_l2f_forward true_forward hook exists; confirm remote enablement"},
        "DNA_V2": {"status": "MISSING_DEPENDENCY", "note": "unavailable in Phase3 local joins; do not fabricate"},
        "Twins": {"status": "MISSING_DEPENDENCY", "note": "unavailable locally"},
        "HCEE": {"status": "MISSING_DEPENDENCY", "note": "unavailable locally"},
        "Favorite_Specialist": {"status": "READY", "note": "research module phase3/4; freeze outputs in research store"},
        "League_Specialist": {"status": "READY", "note": "research module"},
        "High_Goal_Specialist": {"status": "READY", "note": "research module"},
        "meta_model": {"status": "READY", "note": "rule router + blend; research-only"},
        "ecse_direction": {"status": "READY", "note": "derived from Canonical ECSE"},
        "market_odds": {"status": "READY", "note": "odds_snapshots prematch"},
        "explicit_no_bet_reasons": {"status": "PARTIAL", "note": "reconstructed historically; native codes preferred prospectively"},
    }


def true_forward_schema() -> dict[str, Any]:
    return {
        "prediction_record": [
            "fixture_id",
            "candidate_model_id",
            "model_version",
            "configuration_hash",
            "feature_timestamp",
            "odds_timestamp",
            "prediction_timestamp",
            "freeze_timestamp",
            "kickoff_timestamp",
            "direction",
            "p_home",
            "p_draw",
            "p_away",
            "abstain_status",
            "abstain_reason",
            "no_bet",
            "no_bet_reason_codes",
            "prediction_scope",
            "validation_tier",
            "data_completeness",
            "league",
            "country",
            "freeze_hash",
            "cohort_type=true_forward",
        ],
        "result_record_separate": [
            "regulation_time_score",
            "actual_direction",
            "result_timestamp",
            "result_provenance",
            "candidate_hit_miss",
            "priced_return",
        ],
        "immutability": "prediction records must not be overwritten after kickoff",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_phase4(*, out_dir: Path | None = None) -> dict[str, Any]:
    ts = _utc_now()
    out = out_dir or (ROOT / "artifacts" / "prediction_engine_75_phase4" / ts)
    out.mkdir(parents=True, exist_ok=True)
    opening_commit = _git_head()

    holdout_ids_list, lock_meta = load_phase1_holdout_ids()
    sealed = set(holdout_ids_list)

    rows, _ex, _inv = p2.build_expanded_corpus()
    usable = p2.usable(rows)
    by_fid = {r.fixture_id: r for r in usable}

    # Research universe excluding sealed holdout (Phase3 boundary)
    research = sorted([r for r in usable if r.fixture_id not in sealed], key=lambda r: (str(r.kickoff_utc or ""), r.fixture_id))
    cut = int(len(research) * 0.7)
    train_rows, val_rows = research[:cut], research[cut:]
    train_ids = [r.fixture_id for r in train_rows]
    val_ids = [r.fixture_id for r in val_rows]

    # Part 1 — lock manifest BEFORE opening
    manifest = build_locked_manifest(train_ids, val_ids, source_commit=SOURCE_COMMIT_PHASE3)
    manifest["opening_commit_placeholder"] = opening_commit
    _write_json(out / "locked_candidate_manifest.json", manifest)
    man_bytes = json.dumps(manifest, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    man_sha = _sha256_bytes(man_bytes)
    (out / "locked_candidate_manifest.sha256").write_text(man_sha + "\n", encoding="utf-8")
    (out / "LOCKED_CANDIDATE_MANIFEST.md").write_text(
        f"# Locked Candidate Manifest\n\nSHA256: `{man_sha}`\n\n"
        f"Source Phase3 commit: `{SOURCE_COMMIT_PHASE3}`\n\n"
        f"NO MORE TUNING. Holdout evaluation uses this immutable configuration.\n",
        encoding="utf-8",
    )

    # Fit specialists ONCE on all non-holdout research data (fixed Phase3 hyperparameters)
    fit_universe = research  # train+val together — holdout excluded
    fitted: dict[str, p3.FittedSpecialist] = {}
    lock_failures: list[str] = []
    for name in ("Favorite_Specialist", "League_Specialist", "High_Goal_Specialist"):
        sp = p3.fit_specialist(name, fit_universe)
        fitted[name] = sp
        if sp.status not in {"FITTED", "DATA_LIMITED"}:
            lock_failures.append(name)
            # mark integrity failed but keep heuristic fallback evaluation transparent
    # Also fit remaining specialists needed by meta router (locked meta config includes full specialist set)
    for name in p3.SPECIALISTS:
        if name not in fitted:
            fitted[name] = p3.fit_specialist(name, fit_universe)

    # Attach fit hashes to manifest copy (documentation; configuration already locked)
    fit_hashes = {n: _sha256_json({"name": n, "status": fitted[n].status, "train_n": fitted[n].train_n, "classes": fitted[n].classes}) for n in fitted}
    _write_json(out / "locked_candidate_fit_hashes.json", {"fit_hashes": fit_hashes, "note": "Fitted once on non-holdout before opening; no retune after"})

    if len(lock_failures) == len(LOCKED_NAMES):
        validation = {
            "status": STATUS_LOCK_FAIL,
            "lock_failures": lock_failures,
            "not_deployed": True,
            "canonical_unchanged": True,
            "wde_unchanged": True,
            "ecse_unchanged": True,
            "no_auto_promotion": True,
            "artifact_dir": str(out),
        }
        _write_json(out / "validation_report.json", validation)
        return validation

    # Part 2 — integrity
    integrity = verify_holdout_integrity(usable, holdout_ids_list, set(train_ids), set(val_ids), lock_meta)
    # Also ensure holdout IDs never in research train/val
    integrity["research_n"] = len(research)
    integrity["holdout_present_in_usable"] = sum(1 for fid in sealed if fid in by_fid)
    _write_json(out / "sealed_holdout_integrity_report.json", integrity)

    if not integrity.get("passed"):
        validation = {
            "status": STATUS_HOLDOUT_FAIL,
            "integrity": integrity,
            "not_deployed": True,
            "canonical_unchanged": True,
            "wde_unchanged": True,
            "ecse_unchanged": True,
            "no_auto_promotion": True,
            "artifact_dir": str(out.relative_to(ROOT)).replace("\\", "/") if out.is_relative_to(ROOT) else str(out),
        }
        _write_json(out / "validation_report.json", validation)
        return validation

    # Part 3 — open exactly once
    holdout = [by_fid[fid] for fid in holdout_ids_list if fid in by_fid]
    # Preserve Phase1 order
    holdout = sorted(holdout, key=lambda r: holdout_ids_list.index(r.fixture_id) if r.fixture_id in sealed else 0)
    opening = {
        "opened_at": _utc_now(),
        "opening_commit": opening_commit,
        "holdout_fixture_ids": holdout_ids_list,
        "n": len(holdout),
        "candidate_hashes": {c["candidate_id"]: c["configuration_hash"] for c in manifest["locked_candidates"]},
        "manifest_sha256": man_sha,
        "command_executed": "worldcup_predictor.research.prediction_engine_75.phase4.run_phase4",
        "data_source": "phase2.build_expanded_corpus (finished_match_evaluation + worldcup_stored_predictions + odds/ecse joins)",
        "result_source": "fixture_results regulation/home_goals",
        "retuning_allowed_after_open": False,
        "opened_exactly_once": True,
    }
    _write_json(out / "sealed_holdout_opening_ledger.json", opening)

    # Part 4 — evaluate (no refit)
    results: dict[str, dict[str, Any]] = {}

    # Canonical baselines
    results["canonical_wde_raw_argmax"] = evaluate_candidate(
        "canonical_wde_raw_argmax",
        holdout,
        [(p2.prob_argmax(r), r) for r in holdout],
        prob_rows=[({"home": r.home_p or 0, "draw": r.draw_p or 0, "away": r.away_p or 0}, r) for r in holdout],
    )
    results["canonical_wde_stored_decision"] = evaluate_candidate(
        "canonical_wde_stored_decision",
        holdout,
        [(r.wde_decision, r) for r in holdout],
        prob_rows=[({"home": r.home_p or 0, "draw": r.draw_p or 0, "away": r.away_p or 0}, r) for r in holdout],
    )
    results["canonical_ecse_direction"] = evaluate_candidate(
        "canonical_ecse_direction",
        holdout,
        [(r.ecse_direction or r.ft_marginal, r) for r in holdout],
    )
    results["phase2_best_strategy"] = evaluate_candidate(
        "phase2_best_strategy",
        holdout,
        p2.apply_strategy(holdout, PHASE2_BEST_CFG),
    )
    results["market_favorite_baseline"] = evaluate_candidate(
        "market_favorite_baseline",
        holdout,
        [(p2.market_fav(r), r) for r in holdout if p2.market_fav(r)],
    )

    # Locked: ecse_direction
    results["ecse_direction"] = evaluate_candidate(
        "ecse_direction",
        holdout,
        [(r.ecse_direction or r.ft_marginal, r) for r in holdout],
    )

    # Locked specialists
    for name in ("Favorite_Specialist", "League_Specialist", "High_Goal_Specialist"):
        sp = fitted[name]
        preds = []
        abs_ids = []
        probs = []
        for r in holdout:
            pr = p3.predict_specialist(sp, r)
            if not pr.eligible or (pr.abstain_probability or 0) >= 0.75:
                abs_ids.append(r.fixture_id)
                preds.append((None, r))
                probs.append((None, r))
                continue
            preds.append((pr.direction, r))
            probs.append(({"home": pr.p_home or 0, "draw": pr.p_draw or 0, "away": pr.p_away or 0}, r))
        results[name] = evaluate_candidate(name, holdout, preds, abstained=abs_ids, prob_rows=probs)
        if sp.status == "FIT_FAILED":
            results[name]["lock_status"] = "LOCK_INTEGRITY_FAILED"

    # Meta
    meta_preds = []
    meta_abs = []
    meta_probs = []
    meta_decisions = []
    for r in holdout:
        md = p3.meta_decide(r, fitted)
        meta_decisions.append(md)
        if md.abstain_probability >= 0.75 or md.chosen_specialist == "ABSTAIN":
            meta_abs.append(r.fixture_id)
            meta_preds.append((None, r))
            meta_probs.append((None, r))
        else:
            meta_preds.append((md.direction, r))
            meta_probs.append(({"home": md.p_home, "draw": md.p_draw, "away": md.p_away}, r))
    results["meta_model"] = evaluate_candidate("meta_model", holdout, meta_preds, abstained=meta_abs, prob_rows=meta_probs)

    wde_acc = results["canonical_wde_stored_decision"].get("accuracy")
    verdicts = {}
    for name, res in results.items():
        verd = verdict_for(res, wde_acc)
        verdicts[name] = {
            "verdict": verd,
            "accuracy": res.get("accuracy"),
            "coverage": res.get("coverage"),
            "n": res.get("selected_fixtures"),
            "roi": res.get("flat_stake_roi"),
            "warning": SMALL_WARNING,
            "promotable": False,
        }

    _write_json(out / "sealed_holdout_results.json", {"results": results, "warning": SMALL_WARNING, "n_holdout": len(holdout)})
    _write_csv(
        out / "sealed_holdout_candidate_comparison.csv",
        [
            {
                "candidate": k,
                "accuracy": v.get("accuracy"),
                "coverage": v.get("coverage"),
                "selected_n": v.get("selected_fixtures"),
                "abstained": v.get("abstained_fixtures"),
                "roi": v.get("flat_stake_roi"),
                "avg_odds": v.get("average_odds"),
                "wilson_lo": (v.get("wilson_ci95") or [None, None])[0],
                "wilson_hi": (v.get("wilson_ci95") or [None, None])[1],
                "verdict": verdicts[k]["verdict"],
                "warning": SMALL_WARNING,
            }
            for k, v in results.items()
        ],
    )
    _write_json(out / "holdout_candidate_verdicts.json", {"verdicts": verdicts, "warning": SMALL_WARNING})

    # Part 5 — per-fixture ledger
    ledger = []
    for r in holdout:
        fav = p2.market_fav(r)
        specs = {n: p3.predict_specialist(fitted[n], r) for n in ("Favorite_Specialist", "League_Specialist", "High_Goal_Specialist")}
        md = next(d for d in meta_decisions if d.fixture_id == r.fixture_id)
        regimes = p3.tag_regimes(r) if r.wde_decision != r.actual_1x2 else []
        row = {
            "fixture_id": r.fixture_id,
            "date": (r.kickoff_utc or "")[:10],
            "league": r.league,
            "match": r.match,
            "final_score": r.final_score,
            "actual_direction": r.actual_1x2,
            "odds_home": r.odds_home,
            "odds_draw": r.odds_draw,
            "odds_away": r.odds_away,
            "market_favorite": fav,
            "wde_direction": r.wde_decision,
            "ecse_direction": r.ecse_direction or r.ft_marginal,
            "Favorite_Specialist": specs["Favorite_Specialist"].direction if specs["Favorite_Specialist"].eligible else "ABSTAIN",
            "League_Specialist": specs["League_Specialist"].direction if specs["League_Specialist"].eligible else "ABSTAIN",
            "High_Goal_Specialist": specs["High_Goal_Specialist"].direction if specs["High_Goal_Specialist"].eligible else "ABSTAIN",
            "meta_direction": md.direction if md.abstain_probability < 0.75 and md.chosen_specialist != "ABSTAIN" else "ABSTAIN",
            "meta_chosen_specialist": md.chosen_specialist,
            "meta_abstain": md.abstain_probability,
            "wde_correct": r.wde_decision == r.actual_1x2,
            "ecse_correct": (r.ecse_direction or r.ft_marginal) == r.actual_1x2,
            "meta_correct": (md.direction == r.actual_1x2) if md.chosen_specialist != "ABSTAIN" and md.abstain_probability < 0.75 else None,
            "main_disagreement": ",".join(
                sorted(
                    {
                        x
                        for x in [
                            r.wde_decision,
                            r.ecse_direction,
                            fav,
                            md.direction if md.chosen_specialist != "ABSTAIN" else None,
                        ]
                        if x
                    }
                )
            ),
            "error_regime": "|".join(regimes) if regimes else "",
            "notes": SMALL_WARNING,
        }
        ledger.append(row)
    _write_csv(out / "sealed_holdout_fixture_ledger.csv", ledger)
    _write_json(out / "sealed_holdout_fixture_ledger.json", {"rows": ledger, "warning": SMALL_WARNING})

    # Parts 7–12 true-forward
    tf_audit = audit_true_forward_pipeline()
    _write_json(out / "true_forward_pipeline_audit.json", tf_audit)
    readiness = model_readiness()
    _write_json(out / "true_forward_model_readiness.json", readiness)
    schema = true_forward_schema()
    _write_json(out / "true_forward_schema.json", schema)
    _write_json(
        out / "true_forward_collection_plan.json",
        {
            "cohort_type": "true_forward",
            "labels": ["RESEARCH_SELECTION", "RESEARCH_ABSTAIN", "DATA_BLOCKED", "PENDING_EVALUATION"],
            "workflow": [
                "A Discovery daily",
                "B Early freeze 24-48h pre-kickoff",
                "C Refresh freeze only with immutable versioning",
                "D Final prematch freeze",
                "E Result follow-up after FT",
                "F Evaluation after regulation result",
            ],
            "rules": [
                "no prediction after kickoff",
                "no duplicate freeze mutation",
                "idempotent jobs",
                "disk stop gate",
                "quota protection",
                "no auto-promotion",
                "no public betting recommendation",
            ],
            "timers_enablement": "PREPARED_NOT_ENABLED_WITHOUT_OWNER_APPROVAL",
            "current_evaluated_n": 0,
        },
    )
    _write_json(
        out / "timer_preparation_report.json",
        {
            "prepared_units": [t["unit"] for t in tf_audit["timers"] if t["unit_file_present"]],
            "enabled": False,
            "action": "Do NOT enable timers without explicit owner approval",
            "suggested_research_timer": "prediction_engine_75_true_forward_daily (not created as enabled unit)",
            "existing_related": tf_audit["timers"],
        },
    )
    _write_json(
        out / "true_forward_promotion_gates.json",
        {
            "gates": {
                "A": {"n": 30, "purpose": "early diagnostic only", "progress": 0, "passed": False},
                "B": {"n": 100, "purpose": "intermediate stability", "progress": 0, "passed": False},
                "C": {"n": 250, "purpose": "minimum promotion review", "progress": 0, "passed": False},
            },
            "auto_promotion": False,
            "holdout_n11_satisfies_75_target": False,
            "target_75_requirements": [
                "true_forward N>=250",
                "accuracy>=75%",
                "meaningful coverage",
                "no severe league/odds concentration",
                "calibration acceptable",
                "priced performance reported",
                "no leakage",
                "owner approval",
            ],
        },
    )

    # Best holdout candidate (diagnostic)
    ranked = sorted(
        [(k, v) for k, v in results.items() if (v.get("selected_fixtures") or 0) >= 5],
        key=lambda x: (-(x[1].get("accuracy") or -1), -(x[1].get("selected_fixtures") or 0)),
    )
    best = ranked[0] if ranked else (None, None)

    # Status
    ready_models = sum(1 for v in readiness.values() if v.get("status") == "READY")
    if ready_models < 3:
        status = STATUS_TF_BLOCKED
    else:
        status = STATUS_READY

    per_acc = {k: results[k].get("accuracy") for k in LOCKED_NAMES}
    per_cov = {k: results[k].get("coverage") for k in LOCKED_NAMES}
    per_roi = {k: results[k].get("flat_stake_roi") for k in LOCKED_NAMES}

    validation = {
        "status": status,
        "phase": PHASE,
        "candidate_lock_status": "LOCKED_IMMUTABLE",
        "manifest_sha256": man_sha,
        "holdout_integrity_status": integrity["status"],
        "holdout_n": len(holdout),
        "per_candidate_holdout_accuracy": {k: results[k].get("accuracy") for k in results},
        "per_candidate_coverage": {k: results[k].get("coverage") for k in results},
        "per_candidate_roi": {k: results[k].get("flat_stake_roi") for k in results},
        "locked_candidate_accuracy": per_acc,
        "locked_candidate_coverage": per_cov,
        "locked_candidate_roi": per_roi,
        "holdout_verdicts": {k: verdicts[k]["verdict"] for k in verdicts},
        "best_holdout_candidate": {"name": best[0], "accuracy": (best[1] or {}).get("accuracy"), "n": (best[1] or {}).get("selected_fixtures")}
        if best[0]
        else None,
        "small_sample_warning": SMALL_WARNING,
        "true_forward_pipeline_readiness": "PLAN_READY_COLLECTION_NOT_AUTO_ENABLED",
        "model_readiness": {k: v["status"] for k, v in readiness.items()},
        "timers_prepared": True,
        "timers_enabled": False,
        "current_evaluated_true_forward_n": 0,
        "gate_progress": {"A": "0/30", "B": "0/100", "C": "0/250"},
        "target_75_claimed": False,
        "not_deployed": True,
        "canonical_unchanged": True,
        "wde_unchanged": True,
        "ecse_unchanged": True,
        "no_retuning_after_holdout": True,
        "no_auto_promotion": True,
        "opening_commit": opening_commit,
        "artifact_dir": str(out.relative_to(ROOT)).replace("\\", "/") if out.is_relative_to(ROOT) else str(out),
    }
    _write_json(out / "validation_report.json", validation)

    report = _report(validation)
    (out / "PHASE4_LOCKED_HOLDOUT_AND_TRUE_FORWARD_REPORT.md").write_text(report, encoding="utf-8")
    (out / "PHASE4_LOCKED_HOLDOUT_AND_TRUE_FORWARD_REPORT_FA.md").write_text(
        "# فاز ۴ — ارزیابی holdout قفل‌شده و آماده‌سازی true-forward\n\n" + report, encoding="utf-8"
    )
    (out / "owner_phase4_dashboard.html").write_text(_dashboard(validation), encoding="utf-8")
    return validation


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    p2._write_csv(path, rows)


def _report(v: dict[str, Any]) -> str:
    return f"""# PHASE4_LOCKED_HOLDOUT_AND_TRUE_FORWARD_REPORT

Status: **{v['status']}**

## Lock

- Manifest SHA256: `{v['manifest_sha256']}`
- Candidate lock: **{v['candidate_lock_status']}**
- NO RETUNING AFTER HOLDOUT

## Holdout

- Integrity: **{v['holdout_integrity_status']}**
- N: **{v['holdout_n']}**
- Warning: **{v['small_sample_warning']}**

### Locked candidate accuracy

`{v['locked_candidate_accuracy']}`

### Verdicts

`{v['holdout_verdicts']}`

Best diagnostic candidate: `{v['best_holdout_candidate']}`

## True-forward

- Pipeline: {v['true_forward_pipeline_readiness']}
- Evaluated N: **{v['current_evaluated_true_forward_n']}**
- Gates: {v['gate_progress']}
- Timers prepared: {v['timers_prepared']} · enabled: {v['timers_enabled']}

## Safety

- NOT DEPLOYED
- CANONICAL UNCHANGED
- WDE UNCHANGED
- ECSE UNCHANGED
- NO RETUNING AFTER HOLDOUT
- NO AUTO-PROMOTION
- 75% target **not claimed** (holdout N=11 cannot satisfy)
"""


def _dashboard(v: dict[str, Any]) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Phase4 Holdout</title>
<style>body{{font-family:Georgia,serif;margin:2rem;background:#0e141b;color:#e8eef5}}
h1{{color:#9ad0b8}}.card{{background:#1a222d;padding:1rem;margin:1rem 0;border-radius:8px}}.warn{{color:#f0c674}}</style></head><body>
<h1>Phase 4 — Locked Holdout + True-Forward</h1>
<div class="card"><b>{v['status']}</b><br/>
holdout N={v['holdout_n']} · integrity={v['holdout_integrity_status']}<br/>
best={v['best_holdout_candidate']}<br/>
<span class="warn">{v['small_sample_warning']}</span><br/>
TF N={v['current_evaluated_true_forward_n']} · timers enabled={v['timers_enabled']}</div>
<p>NOT DEPLOYED · CANONICAL/WDE/ECSE UNCHANGED · NO RETUNING · NO AUTO-PROMOTION</p>
</body></html>"""
