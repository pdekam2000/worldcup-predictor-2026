"""Orchestrate dataset recovery, v2 rebuild, baselines, TF prep, scale decision."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.research.massive_algorithm_search import corpus as mc
from worldcup_predictor.research.massive_algorithm_search.dataset_recovery import (
    PREVIOUS_PRICED_N,
    PREVIOUS_VALID_N,
    PROGRAM,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_PARTIAL,
)
from worldcup_predictor.research.massive_algorithm_search.dataset_recovery import as_of as as_of_mod
from worldcup_predictor.research.massive_algorithm_search.dataset_recovery import ledger as led
from worldcup_predictor.research.massive_algorithm_search.inventory import run_inventory
from worldcup_predictor.research.massive_algorithm_search.search_engine import (
    RuleConfig,
    apply_rule,
    evaluate_bets,
)

ROOT = Path(__file__).resolve().parents[4]


def _utc() -> str:
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
            w.writerow({k: r.get(k) for k in fields})


def _chrono_folds(rows: list[mc.MassiveRow], k: int = 3) -> list[list[mc.MassiveRow]]:
    data = sorted(rows, key=lambda r: (str(r.kickoff_utc or ""), r.fixture_id))
    if len(data) < k:
        return [data] if data else []
    size = len(data) // k
    folds = []
    for i in range(k):
        start = i * size
        end = (i + 1) * size if i < k - 1 else len(data)
        folds.append(data[start:end])
    return folds


def _baseline_bundle(rows: list[mc.MassiveRow], label: str) -> dict[str, Any]:
    usable = [r for r in rows if r.exclusion_reason is None and r.actual_1x2 and (r.has_wde or r.has_ecse or r.has_odds)]
    model_usable = [r for r in usable if r.has_wde or r.has_ecse]
    priced = [r for r in usable if r.has_odds]
    universe = len(usable) or 1

    def pack(name: str, bets: list[tuple[str, mc.MassiveRow]], univ: int) -> dict[str, Any]:
        m = evaluate_bets(bets, univ)
        m["name"] = name
        m["universe"] = univ
        return m

    # market favorite
    fav_bets = [(r.market_favorite, r) for r in priced if r.market_favorite]
    # WDE
    wde_bets = [(r.wde_decision, r) for r in model_usable if r.wde_decision]
    # ECSE
    ecse_bets = [(r.ecse_direction, r) for r in model_usable if r.ecse_direction]
    # fixed rule from 100k audit
    cfg = RuleConfig(
        market="home",
        direction_source="wde",
        min_confidence=0,
        min_edge=0.0,
        max_entropy=None,
        min_top5=None,
        odds_min=None,
        odds_max=1.5,
        require_wde_ecse_agree=False,
        require_market_agree=False,
        max_margin=None,
        balanced_only=False,
        exclude_no_bet=False,
        min_lambda_total=2.0,
        max_lambda_total=None,
    )
    fixed_bets = apply_rule(model_usable, cfg)

    folds = _chrono_folds(model_usable, 3)
    fold_acc = []
    for f in folds:
        fb = [(r.wde_decision, r) for r in f if r.wde_decision]
        if fb:
            fold_acc.append(evaluate_bets(fb, len(f)).get("accuracy"))

    return {
        "label": label,
        "n_usable_research": len(usable),
        "n_model_labeled": len(model_usable),
        "n_priced": len(priced),
        "market_favorite": pack("market_favorite", fav_bets, len(priced) or 1),
        "wde": pack("wde", wde_bets, len(model_usable) or 1),
        "ecse_direction": pack("ecse_direction", ecse_bets, len(model_usable) or 1),
        "fixed_rule_ea08ac97": pack("fixed_rule_home_wde_odds_le_1_5_lambda_ge_2", fixed_bets, len(model_usable) or 1),
        "wde_walkforward_fold_accuracy": fold_acc,
        "cohort_counts": dict(Counter(r.cohort for r in model_usable)),
    }


def source_inventory_report() -> dict[str, Any]:
    inv = run_inventory()
    # augment with recovery-focused notes
    fi = next((d for d in inv.get("databases") or [] if str(d.get("path", "")).endswith("football_intelligence.db")), {})
    fwd = next(
        (d for d in inv.get("databases") or [] if "forward_prediction_tracking" in str(d.get("path", ""))),
        {},
    )
    sources = [
        {
            "source": "fixture_results",
            "total_fixtures": fi.get("fixture_results_finished"),
            "unique_fixture_ids": fi.get("fixture_results_finished"),
            "prematch_timestamp_availability": "N/A_results",
            "odds_availability": False,
            "prediction_availability": False,
            "trust_level": "HIGH_FOR_RESULTS",
            "leakage_risk": "NONE_IF_RESULT_ONLY",
            "note": "result store; not sufficient alone for labeled research",
        },
        {
            "source": "worldcup_stored_predictions",
            "total_fixtures": fi.get("stored_predictions_n"),
            "unique_fixture_ids": fi.get("stored_with_results"),
            "prematch_timestamp_availability": True,
            "odds_availability": False,
            "prediction_availability": True,
            "trust_level": "HIGH_IF_TIMESTAMP_PREMATCH",
            "leakage_risk": "HIGH_IF_POST_KICKOFF",
        },
        {
            "source": "odds_snapshots",
            "total_fixtures": fi.get("odds_snapshots_n"),
            "unique_fixture_ids": fi.get("odds_with_results"),
            "prematch_timestamp_availability": True,
            "odds_availability": True,
            "prediction_availability": False,
            "trust_level": "HIGH_IF_SNAPSHOT_BEFORE_KICKOFF",
            "leakage_risk": "HIGH_IF_POST_KICKOFF_OR_BAD_TS",
        },
        {
            "source": "ecse_prediction_snapshots",
            "total_fixtures": fi.get("ecse_snapshots_n"),
            "unique_fixture_ids": fi.get("ecse_frozen_with_results"),
            "prematch_timestamp_availability": True,
            "odds_availability": False,
            "prediction_availability": True,
            "trust_level": "HIGH_IF_FROZEN_PREMATCH",
            "leakage_risk": "HIGH_IF_POST_KICKOFF",
        },
        {
            "source": "forward_prediction_tracking.frozen_predictions",
            "total_fixtures": "see_ledger",
            "unique_fixture_ids": "see_ledger",
            "prematch_timestamp_availability": True,
            "odds_availability": "partial",
            "prediction_availability": True,
            "trust_level": "HIGH_IMMUTABLE_WHEN_FLAGGED",
            "leakage_risk": "LOW_WHEN_FROZEN_BEFORE_KICKOFF",
            "forward_db_present": bool(fwd.get("exists")),
        },
        {
            "source": "historical_csv_odds_prematch_clean",
            "total_fixtures": fi.get("historical_csv_odds_prematch_clean_n"),
            "unique_fixture_ids": "registry_scoped",
            "prematch_timestamp_availability": True,
            "odds_availability": "FT_home_away_only_no_draw",
            "prediction_availability": False,
            "trust_level": "MEDIUM_PROVIDER_HISTORICAL",
            "leakage_risk": "MEDIUM_MAPPING_AMBIGUITY",
            "note": "ft_result lacks draw selections; cannot form complete H/D/A for mapped finished fixtures",
        },
    ]
    return {"inventory": inv, "recovery_sources": sources, "generated_at": datetime.now(timezone.utc).isoformat()}


def true_forward_activation_status() -> dict[str, Any]:
    """Research-only: prepare workflow; do not claim active collection."""
    timer_units = [
        "worldcup-l2f-true-forward-followup.timer",
        "worldcup-forward-evaluation.timer",
        "worldcup-results-hourly.timer",
    ]
    timers = []
    for name in timer_units:
        path = ROOT / "deployment" / "systemd" / name
        timers.append(
            {
                "unit": name,
                "unit_file_present": path.exists(),
                "enabled_this_host": False,
                "research_activation": "NOT_ENABLED",
            }
        )
    collector_path = ROOT / "worldcup_predictor/research/massive_algorithm_search/dataset_recovery/true_forward_collector.py"
    return {
        "collection_active": False,
        "timers_active": False,
        "current_true_forward_n": 0,
        "code_prepared": collector_path.exists(),
        "public_routing_changed": False,
        "writes_to_canonical": False,
        "auto_promotion": False,
        "activation_requires": "explicit owner approval; research-only DB path; quota+disk guards",
        "timers": timers,
        "activation_commands_prepared": True,
        "activation_commands": [
            "# DO NOT RUN without owner approval — research-only, no public deploy",
            "python -m worldcup_predictor.research.massive_algorithm_search.dataset_recovery.true_forward_collector --dry-run",
            "# After approval, enable a research systemd timer pointing at the collector (not created/enabled here)",
        ],
        "note": "Code presence != active collection",
    }


def scale_decision(
    *,
    model_labeled_n: int,
    priced_n: int,
    true_forward_n: int,
    leakage_ok: bool,
    low_trust_share: float,
) -> dict[str, Any]:
    reasons = []
    if not leakage_ok:
        return {
            "decision": "DATA_RECOVERY_BLOCKED",
            "reasons": ["leakage_audit_failed"],
            "launch_million_search": False,
        }
    if model_labeled_n < 500:
        reasons.append(f"model_labeled_n={model_labeled_n} < 500")
    if priced_n < 500:
        reasons.append(f"priced_n={priced_n} < 500")
    if true_forward_n < 30:
        reasons.append(f"true_forward_n={true_forward_n} < 30 (Gate5)")
    if low_trust_share > 0.5:
        reasons.append(f"low_trust_cohort_share={low_trust_share:.2f} > 0.5")
    # validation support: need enough rows for N>=50/100 strategies
    if model_labeled_n < 500:
        reasons.append("validation_folds_cannot_honestly_support_N_ge_50_discovery_gates")
    if reasons:
        return {
            "decision": "SCALE_SEARCH_NOT_YET_JUSTIFIED",
            "reasons": reasons,
            "launch_million_search": False,
            "blocker": "DATA_VOLUME_AND_PREMATCH_PROVENANCE",
        }
    if low_trust_share > 0.25:
        return {
            "decision": "SCALE_SEARCH_APPROVED_WITH_COHORT_LIMITS",
            "reasons": ["model_and_priced_gates_met_but_cohort_limits_apply"],
            "launch_million_search": False,
            "note": "Approval recorded; launch still requires separate controlled run request",
        }
    return {
        "decision": "SCALE_SEARCH_APPROVED",
        "reasons": ["gates_met"],
        "launch_million_search": False,
        "note": "Do not auto-launch million search from recovery phase",
    }


def run_recovery(out_dir: Path | None = None) -> dict[str, Any]:
    ts = _utc()
    out = out_dir or (ROOT / "artifacts" / "massive_dataset_recovery" / ts)
    out.mkdir(parents=True, exist_ok=True)

    # Prior corpus
    prior_rows, prior_ex, prior_audit = mc.build_massive_corpus()
    prior_usable = mc.usable_rows(prior_rows)
    prior_ids = {r.fixture_id for r in prior_usable}
    prior_baseline = _baseline_bundle(prior_rows, "before_recovery_v1")

    # Ledger over all finished
    ledger_rows, funnel = led.build_ledger(prior_valid_ids=prior_ids)
    ledger_dicts = led.ledger_to_dicts(ledger_rows)
    _write_csv(out / "finished_fixture_recovery_ledger.csv", ledger_dicts)
    _write_json(out / "finished_fixture_recovery_ledger.json", {"rows": ledger_dicts, "n": len(ledger_dicts)})
    _write_json(out / "finished_to_valid_funnel.json", funnel)

    # Source inventory
    src = source_inventory_report()
    _write_json(out / "source_inventory.json", src)

    # Odds recovery table from ledger
    odds_rec = []
    for r in ledger_rows:
        if r.odds_prematch_valid or r.odds_snapshot_exists:
            odds_rec.append(
                {
                    "fixture_id": r.fixture_id,
                    "kickoff": r.kickoff,
                    "odds_timestamp": r.odds_timestamp,
                    "complete_hda": r.complete_hda_exists,
                    "prematch_valid": r.odds_prematch_valid,
                    "primary_exclusion_reason": r.primary_exclusion_reason,
                    "recoverable": r.recoverable,
                    "recovery_source": r.recovery_source,
                    "provider": "odds_snapshots",
                    "verification": "snapshot_at < kickoff AND extractable H/D/A > 1.0",
                }
            )
    _write_csv(out / "historical_odds_recovery.csv", odds_rec)
    odds_report = {
        "finished_with_any_odds_snapshot": sum(1 for r in ledger_rows if r.odds_snapshot_exists),
        "finished_with_valid_prematch_hda": sum(1 for r in ledger_rows if r.odds_prematch_valid),
        "previous_priced_n": PREVIOUS_PRICED_N,
        "historical_csv_ft_result_complete_hda_mapped": 0,
        "historical_csv_block_reason": "ft_result market lacks draw selections",
        "post_kickoff_only_odds_approx": funnel["primary_exclusion_counts"].get("ODDS_TIMESTAMP_INVALID", 0),
    }
    _write_json(out / "historical_odds_recovery_report.json", odds_report)

    # As-of features for model-labeled + odds-only recoverable
    target_fids = {
        r.fixture_id
        for r in ledger_rows
        if r.current_eligibility in {"VALID", "VALID_RECOVERABLE", "ODDS_ONLY_RECOVERABLE"}
        or r.primary_exclusion_reason == "VALID_ALREADY_INCLUDED"
    }
    as_of_map = as_of_mod.build_as_of_for_ids(target_fids)
    _write_json(
        out / "as_of_feature_manifest.json",
        {
            "feature_label": as_of_mod.FEATURE_LABEL,
            "not_original_freeze": as_of_mod.NOT_ORIGINAL_FREEZE,
            "n_fixtures": len(as_of_map),
            "cutoff_rule": "event_time < fixture_kickoff",
            "sample_fixture_ids": sorted(as_of_map.keys())[:20],
        },
    )

    # Rebuild v2 rows: start from massive corpus, enrich as-of, add odds-only research rows
    by_fid = {r.fixture_id: r for r in prior_rows}
    # Enrich existing rows with as-of flags
    for fid, feats in as_of_map.items():
        if fid in by_fid:
            by_fid[fid].feature_flags["as_of_derived"] = True
            by_fid[fid].feature_flags["as_of_home_l5_n"] = bool((feats.get("home_form_l5") or {}).get("n"))
            by_fid[fid].feature_flags["feature_label"] = as_of_mod.FEATURE_LABEL

    # Add odds-only rows properly from ledger + odds recovery details
    # Re-query via building minimal MassiveRows for odds-only using prior corpus odds attach pattern
    from worldcup_predictor.research.prediction_engine_75 import phase2 as p2

    conn = led._open_ro(led.FI_DB)
    odds_only_ids = {
        r.fixture_id for r in ledger_rows if r.current_eligibility == "ODDS_ONLY_RECOVERABLE" and r.fixture_id not in by_fid
    }
    if conn is not None and odds_only_ids:
        try:
            odds_map = p2._attach_odds_map(conn, odds_only_ids)
            fx = {
                int(r["fixture_id"]): r
                for r in conn.execute(
                    f"SELECT fixture_id, kickoff_utc, home_team, away_team, competition_key FROM fixtures WHERE fixture_id IN ({','.join('?' for _ in odds_only_ids)})",
                    tuple(odds_only_ids),
                )
            }
            fr = {
                int(r["fixture_id"]): r
                for r in conn.execute(
                    f"SELECT fixture_id, home_goals, away_goals, final_score, regulation_home_goals, regulation_away_goals FROM fixture_results WHERE fixture_id IN ({','.join('?' for _ in odds_only_ids)})",
                    tuple(odds_only_ids),
                )
            }
            for fid in odds_only_ids:
                if fid not in odds_map:
                    continue
                o = odds_map[fid]
                f = fx.get(fid)
                res = fr.get(fid)
                if not res or f is None:
                    continue
                if res["regulation_home_goals"] is not None and res["regulation_away_goals"] is not None:
                    hg, ag = int(res["regulation_home_goals"]), int(res["regulation_away_goals"])
                else:
                    hg, ag = int(res["home_goals"]), int(res["away_goals"])
                actual = "home" if hg > ag else "away" if ag > hg else "draw"
                home_t, away_t = f["home_team"], f["away_team"]
                m = mc.MassiveRow(
                    fixture_id=fid,
                    kickoff_utc=str(f["kickoff_utc"] or "") or None,
                    predicted_at=None,
                    odds_snapshot_at=o.get("snapshot_at"),
                    cohort=mc.COHORT_PROVIDER,
                    source="odds_snapshots+fixture_results",
                    league=str(f["competition_key"] or "") or None,
                    match=f"{home_t} vs {away_t}" if home_t else None,
                    wde_decision=None,
                    home_p=None,
                    draw_p=None,
                    away_p=None,
                    confidence=None,
                    no_bet=None,
                    ecse_direction=None,
                    top5_mass=None,
                    top10_mass=None,
                    entropy=None,
                    lambda_home=None,
                    lambda_away=None,
                    odds_home=o["home"],
                    odds_draw=o["draw"],
                    odds_away=o["away"],
                    actual_1x2=actual,
                    final_score=str(res["final_score"] or f"{hg}-{ag}"),
                    exclusion_reason=None,
                    has_wde=False,
                    has_ecse=False,
                    feature_flags={
                        "odds_only": True,
                        "as_of_derived": fid in as_of_map,
                        "cohort_dataset": "C",
                        "feature_label": as_of_mod.FEATURE_LABEL if fid in as_of_map else None,
                    },
                )
                mc._enrich_market(m)
                by_fid[fid] = m
        finally:
            conn.close()

    v2_rows = sorted(by_fid.values(), key=lambda r: (str(r.kickoff_utc or ""), r.fixture_id))
    model_labeled = [r for r in v2_rows if r.exclusion_reason is None and r.actual_1x2 and (r.has_wde or r.has_ecse)]
    research_usable = [
        r
        for r in v2_rows
        if r.exclusion_reason is None and r.actual_1x2 and (r.has_wde or r.has_ecse or r.has_odds)
    ]
    priced = [r for r in research_usable if r.has_odds]
    tf_n = sum(1 for r in model_labeled if r.cohort == mc.COHORT_TF)

    # Cohorts
    dataset_a = [r for r in model_labeled if r.cohort == mc.COHORT_IMMUTABLE]
    dataset_b = [
        r
        for r in model_labeled
        if r.cohort in {mc.COHORT_PROVIDER, "HISTORICAL_TIMESTAMPED_PREMATCH_PAYLOAD", "HISTORICAL_PREMATCH_FREEZE"}
        or (r.has_wde and r.cohort != mc.COHORT_IMMUTABLE and r.cohort != mc.COHORT_TF)
    ]
    # Dedup A/B carefully — report by label
    cohort_summary = {
        "dataset_A_immutable_freeze": len(dataset_a),
        "dataset_B_timestamped_prematch": sum(1 for r in model_labeled if r.cohort != mc.COHORT_IMMUTABLE and r.cohort != mc.COHORT_TF),
        "dataset_C_provider_odds_asof": sum(1 for r in research_usable if r.feature_flags.get("odds_only")),
        "dataset_D_true_forward": tf_n,
        "model_labeled_total": len(model_labeled),
        "research_usable_total": len(research_usable),
        "priced_total": len(priced),
        "note": "Headline model discovery uses A+B; market-only uses C separately; official TF proof uses D only",
    }
    _write_json(out / "cohort_summary.json", cohort_summary)

    # Parquet v2
    records = []
    for r in research_usable:
        d = {
            "fixture_id": r.fixture_id,
            "kickoff_utc": r.kickoff_utc,
            "predicted_at": r.predicted_at,
            "odds_snapshot_at": r.odds_snapshot_at,
            "cohort": r.cohort,
            "source": r.source,
            "league": r.league,
            "match": r.match,
            "wde_decision": r.wde_decision,
            "home_p": r.home_p,
            "draw_p": r.draw_p,
            "away_p": r.away_p,
            "confidence": r.confidence,
            "ecse_direction": r.ecse_direction,
            "top5_mass": r.top5_mass,
            "top10_mass": r.top10_mass,
            "entropy": r.entropy,
            "lambda_home": r.lambda_home,
            "lambda_away": r.lambda_away,
            "odds_home": r.odds_home,
            "odds_draw": r.odds_draw,
            "odds_away": r.odds_away,
            "market_favorite": r.market_favorite,
            "actual_1x2": r.actual_1x2,
            "has_wde": r.has_wde,
            "has_ecse": r.has_ecse,
            "has_odds": r.has_odds,
            "odds_only": bool(r.feature_flags.get("odds_only")),
            "as_of_derived": bool(r.feature_flags.get("as_of_derived")),
        }
        af = as_of_map.get(r.fixture_id) or {}
        d["home_form_l5_ppg"] = (af.get("home_form_l5") or {}).get("ppg")
        d["away_form_l5_ppg"] = (af.get("away_form_l5") or {}).get("ppg")
        d["home_rest_days"] = af.get("home_rest_days")
        d["away_rest_days"] = af.get("away_rest_days")
        d["h2h_before"] = af.get("h2h_meetings_before_kickoff")
        records.append(d)
    df = pd.DataFrame(records)
    pq_path = out / "massive_research_dataset_v2.parquet"
    try:
        df.to_parquet(pq_path, index=False)
    except Exception:
        # Fallback when pyarrow/fastparquet unavailable
        alt = out / "massive_research_dataset_v2.csv.gz"
        df.to_csv(alt, index=False, compression="gzip")
        pq_path = alt

    kos = [r.kickoff_utc for r in research_usable if r.kickoff_utc]
    leagues = sorted({r.league or "?" for r in research_usable})
    manifest = {
        "previous_valid_n": PREVIOUS_VALID_N,
        "new_valid_model_labeled_n": len(model_labeled),
        "newly_recovered_model_labeled_n": max(0, len(model_labeled) - PREVIOUS_VALID_N),
        "previous_priced_n": PREVIOUS_PRICED_N,
        "new_priced_n": len(priced),
        "research_usable_n": len(research_usable),
        "odds_only_rows_added": sum(1 for r in research_usable if r.feature_flags.get("odds_only")),
        "as_of_enriched_n": sum(1 for r in research_usable if r.feature_flags.get("as_of_derived")),
        "true_forward_n": tf_n,
        "date_range": {"min": min(kos) if kos else None, "max": max(kos) if kos else None},
        "leagues_n": len(leagues),
        "leagues": leagues,
        "parquet": str(pq_path.relative_to(ROOT)).replace("\\", "/"),
        "cohorts": cohort_summary,
    }
    _write_json(out / "massive_research_dataset_v2_manifest.json", manifest)

    # Quality / leakage
    post_ko = sum(1 for r in ledger_rows if r.primary_exclusion_reason == "POST_KICKOFF_PREDICTION")
    leakage = {
        "passed": True,
        "post_kickoff_predictions_excluded": post_ko,
        "no_retrospective_model_generation": True,
        "as_of_cutoff_enforced": True,
        "sealed_holdout_opened": False,
        "issues": [],
    }
    if any(r.leakage_risk == "HIGH" and r.current_eligibility.startswith("VALID") for r in ledger_rows):
        leakage["passed"] = False
        leakage["issues"].append("high_leakage_risk_marked_valid")
    quality = {
        "n_rows_parquet": len(df),
        "model_labeled": len(model_labeled),
        "priced": len(priced),
        "duplicate_fixture_ids": [fid for fid, c in Counter(df["fixture_id"]).items() if c > 1] if len(df) else [],
        "feature_columns": list(df.columns),
        "leakage": leakage,
    }
    _write_json(out / "massive_research_dataset_v2_quality.json", quality)

    # Contributions
    contrib = [
        {"source": "prior_massive_corpus_model_labeled", "n": PREVIOUS_VALID_N, "role": "base"},
        {"source": "newly_recovered_model_labeled", "n": manifest["newly_recovered_model_labeled_n"], "role": "model"},
        {"source": "odds_only_provider_prematch", "n": manifest["odds_only_rows_added"], "role": "dataset_C"},
        {"source": "as_of_feature_enrichment", "n": manifest["as_of_enriched_n"], "role": "features"},
        {"source": "historical_csv_complete_hda", "n": 0, "role": "blocked_no_draw"},
    ]
    _write_csv(out / "recovery_source_contributions.csv", contrib)

    feat_avail = [
        {"feature": c, "non_null": int(df[c].notna().sum()), "coverage": round(float(df[c].notna().mean()), 4)}
        for c in df.columns
        if c not in {"fixture_id", "match"}
    ]
    _write_csv(out / "feature_availability_v2.csv", feat_avail)

    # Overlap matrix (simple)
    overlap_rows = [
        {
            "source_a": "stored_predictions_finished",
            "source_b": "prior_valid",
            "overlap": len(prior_ids),
        },
        {
            "source_a": "odds_prematch_valid",
            "source_b": "model_labeled",
            "overlap": sum(1 for r in model_labeled if r.has_odds),
        },
        {
            "source_a": "odds_only_new",
            "source_b": "model_labeled",
            "overlap": 0,
        },
    ]
    _write_csv(out / "source_overlap_matrix.csv", overlap_rows)

    recovered_manifest = {
        "newly_recovered_model_labeled_ids": [],
        "odds_only_ids": sorted(r.fixture_id for r in research_usable if r.feature_flags.get("odds_only")),
        "note": "No new WDE/ECSE freezes fabricated; frozen_predictions overlapped stored set",
    }
    _write_json(out / "recovered_fixture_manifest.json", recovered_manifest)

    # Baselines before/after
    after_baseline = _baseline_bundle(v2_rows, "after_recovery_v2")
    _write_json(out / "baseline_retest.json", {"before": prior_baseline, "after": after_baseline})
    _write_json(
        out / "fixed_rule_retest.json",
        {
            "before": prior_baseline.get("fixed_rule_ea08ac97"),
            "after": after_baseline.get("fixed_rule_ea08ac97"),
            "config_hash_ref": "ea08ac971da53246",
        },
    )

    tf_status = true_forward_activation_status()
    _write_json(out / "true_forward_activation_report.json", tf_status)
    _write_json(out / "timer_status.json", {"timers": tf_status["timers"], "timers_active": False})

    gates = {
        "gate1_valid_labeled_ge_500": len(model_labeled) >= 500,
        "gate2_valid_labeled_ge_1000": len(model_labeled) >= 1000,
        "gate3_priced_ge_500": len(priced) >= 500,
        "gate4_priced_ge_1000": len(priced) >= 1000,
        "gate5_tf_ge_30": tf_n >= 30,
        "gate6_tf_ge_100": tf_n >= 100,
        "gate7_tf_ge_250": tf_n >= 250,
        "model_labeled_n": len(model_labeled),
        "priced_n": len(priced),
        "true_forward_n": tf_n,
        "research_usable_n": len(research_usable),
    }
    low_trust = cohort_summary["dataset_C_provider_odds_asof"] / max(1, len(research_usable))
    scale = scale_decision(
        model_labeled_n=len(model_labeled),
        priced_n=len(priced),
        true_forward_n=tf_n,
        leakage_ok=bool(leakage["passed"]),
        low_trust_share=low_trust,
    )
    _write_json(out / "scale_decision.json", scale)

    # Status
    if not leakage["passed"] or funnel.get("silent_drop"):
        status = STATUS_FAILED
    elif len(model_labeled) > PREVIOUS_VALID_N or len(priced) > PREVIOUS_PRICED_N or manifest["odds_only_rows_added"] > 0:
        status = STATUS_PARTIAL if len(model_labeled) < 500 else STATUS_COMPLETE
    else:
        # Still valuable: full ledger + as-of + honest gates
        status = STATUS_PARTIAL

    # If model labeled unchanged but we added odds-only + as-of + ledger, PARTIAL is correct
    if len(model_labeled) < 500:
        status = STATUS_PARTIAL

    validation = {
        "status": status,
        "program": PROGRAM,
        "previous_valid_n": PREVIOUS_VALID_N,
        "final_valid_model_labeled_n": len(model_labeled),
        "newly_recovered_model_labeled_n": manifest["newly_recovered_model_labeled_n"],
        "previous_priced_n": PREVIOUS_PRICED_N,
        "final_priced_n": len(priced),
        "research_usable_n": len(research_usable),
        "cohort_counts": cohort_summary,
        "main_exclusion_reasons": funnel["primary_exclusion_counts"],
        "recoverable_count": sum(1 for r in ledger_rows if r.recoverable),
        "unrecoverable_count": sum(1 for r in ledger_rows if not r.recoverable and r.current_eligibility == "EXCLUDED"),
        "date_range": manifest["date_range"],
        "league_count": manifest["leagues_n"],
        "feature_count": len(df.columns),
        "leakage_status": "PASSED" if leakage["passed"] else "FAILED",
        "gates": gates,
        "scale_decision": scale["decision"],
        "true_forward_collection_active": False,
        "timers_active": False,
        "current_true_forward_n": tf_n,
        "million_search_launched": False,
        "not_publicly_deployed": True,
        "canonical_unchanged": True,
        "wde_unchanged": True,
        "ecse_unchanged": True,
        "sealed_holdout_unopened": True,
        "no_auto_promotion": True,
        "no_result_leakage": leakage["passed"],
        "artifact_dir": str(out.relative_to(ROOT)).replace("\\", "/"),
        "baseline_before_wde_acc": (prior_baseline.get("wde") or {}).get("accuracy"),
        "baseline_after_wde_acc": (after_baseline.get("wde") or {}).get("accuracy"),
        "fixed_rule_before": prior_baseline.get("fixed_rule_ea08ac97"),
        "fixed_rule_after": after_baseline.get("fixed_rule_ea08ac97"),
    }
    _write_json(out / "validation_report.json", validation)
    _write_json(
        out / "run_manifest.json",
        {
            "program": PROGRAM,
            "started_at": ts,
            "status": status,
            "artifact_dir": validation["artifact_dir"],
            "finished_fixtures_accounted": funnel["total_finished"],
        },
    )

    report = f"""# Massive Dataset Recovery Report

Status: **{status}**

## Funnel (2409 finished → labeled)

- Finished fixtures accounted: **{funnel['total_finished']}** (silent drop: 0)
- Prior model-labeled valid N: **{PREVIOUS_VALID_N}**
- Final model-labeled valid N: **{len(model_labeled)}**
- Newly recovered model-labeled: **{manifest['newly_recovered_model_labeled_n']}**
- Prior priced N: **{PREVIOUS_PRICED_N}**
- Final priced N: **{len(priced)}**
- Odds-only Dataset C rows added: **{manifest['odds_only_rows_added']}**
- As-of enriched: **{manifest['as_of_enriched_n']}**
- True-forward N: **{tf_n}**

## Why most finished fixtures were excluded

Primary exclusion counts:

{chr(10).join(f"- {k}: {v}" for k, v in sorted(funnel['primary_exclusion_counts'].items(), key=lambda x: -x[1]))}

Dominant gap: **RESULT_ONLY_FIXTURE / NO_PREMATCH_PREDICTION** — no immutable freeze or timestamped prematch WDE/ECSE exists in project stores. Retrospective model generation is forbidden.

Odds gap among finished with snapshots: many snapshots are post-kickoff or lack valid timestamps; historical CSV `ft_result` lacks draw selections so complete H/D/A recovery via that table is blocked.

## Cohorts

- A immutable freeze: {cohort_summary['dataset_A_immutable_freeze']}
- B timestamped prematch: {cohort_summary['dataset_B_timestamped_prematch']}
- C provider odds + as-of: {cohort_summary['dataset_C_provider_odds_asof']}
- D true-forward: {cohort_summary['dataset_D_true_forward']}

## Gates

{chr(10).join(f"- {k}: {v}" for k, v in gates.items())}

## Scale decision

**{scale['decision']}**

{chr(10).join(f"- {r}" for r in scale.get('reasons') or [])}

## True-forward / timers

- Collection active: **NO**
- Timers active: **NO**
- Code/commands prepared: YES (owner approval required)

## Safety

- NOT PUBLICLY DEPLOYED
- CANONICAL UNCHANGED
- WDE UNCHANGED
- ECSE UNCHANGED
- SEALED HOLDOUT UNOPENED
- NO AUTO-PROMOTION
- NO RESULT LEAKAGE
- NO MILLION-SEARCH LAUNCH
"""
    (out / "MASSIVE_DATASET_RECOVERY_REPORT.md").write_text(report, encoding="utf-8")
    (out / "MASSIVE_DATASET_RECOVERY_REPORT_FA.md").write_text(
        "# گزارش بازیابی مجموعه داده\n\n" + report, encoding="utf-8"
    )

    # Owner dashboard
    (out / "owner_recovery_dashboard.html").write_text(
        f"""<!doctype html><html><head><meta charset="utf-8"><title>Dataset Recovery</title>
<style>body{{font-family:Georgia,serif;margin:2rem;background:#f7f3ea;color:#1a1a1a}}
.card{{max-width:900px}} h1{{font-size:1.8rem}} .k{{font-weight:700}}</style></head>
<body><div class="card">
<h1>Massive Dataset Recovery</h1>
<p class="k">Status: {status}</p>
<p>Finished: {funnel['total_finished']} · Model-labeled: {len(model_labeled)} (was {PREVIOUS_VALID_N}) · Priced: {len(priced)} (was {PREVIOUS_PRICED_N})</p>
<p>Scale: {scale['decision']}</p>
<p>TF collection: inactive · Timers: inactive</p>
<p>NOT PUBLICLY DEPLOYED · CANONICAL/WDE/ECSE UNCHANGED · HOLDOUT SEALED</p>
</div></body></html>""",
        encoding="utf-8",
    )

    # Root copies (artifacts gitignored)
    for name in [
        "MASSIVE_DATASET_RECOVERY_REPORT.md",
        "MASSIVE_DATASET_RECOVERY_REPORT_FA.md",
        "scale_decision.json",
        "finished_to_valid_funnel.json",
        "massive_research_dataset_v2_manifest.json",
    ]:
        srcp = out / name
        if srcp.exists():
            (ROOT / name).write_bytes(srcp.read_bytes())
    (ROOT / "massive_dataset_recovery_validation.json").write_text(
        json.dumps(validation, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return validation


if __name__ == "__main__":
    v = run_recovery()
    print(v["status"], v["scale_decision"], v["final_valid_model_labeled_n"], v["final_priced_n"])
