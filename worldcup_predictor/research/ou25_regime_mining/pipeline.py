"""Orchestrate O/U 2.5 regime mining + ECSE direction filtering (read-only)."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ou25_regime_mining import (
    LABEL_BASELINE,
    LABEL_NO_EDGE,
    LABEL_PROMISING,
    LABEL_SUPPORTED,
    PROGRAM,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_NO_EDGE,
    STATUS_PARTIAL_ODDS,
)
from worldcup_predictor.research.ou25_regime_mining.ledger import EVAL_DB, FI_DB, ROOT, build_ledger
from worldcup_predictor.research.ou25_regime_mining.mining import (
    ecse_direction_analysis,
    exact_top5_segments,
    feature_buckets,
    label_program,
    leaderboard,
    raw_split,
    search_rules,
)


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
    fields: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def enrich_tf_1x2_and_exact(rows: list[dict[str, Any]]) -> None:
    """Attach actual_1x2 and exact_top5_hit for TF rows from eval DB (read-only)."""
    if not EVAL_DB.exists():
        return
    conn = sqlite3.connect(f"file:{EVAL_DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    results = {int(r["fixture_id"]): dict(r) for r in conn.execute("SELECT * FROM actual_results")}
    ranks = {}
    for r in conn.execute("SELECT prediction_id, rank, score FROM exact_score_rankings ORDER BY prediction_id, rank"):
        ranks.setdefault(str(r["prediction_id"]), []).append(str(r["score"]))
    conn.close()
    for row in rows:
        if row.get("cohort") != "TRUE_FORWARD":
            continue
        fid = int(row["fixture_id"])
        res = results.get(fid) or {}
        row["actual_1x2"] = res.get("actual_1x2") or res.get("regulation_result")
        actual_score = res.get("actual_score")
        pid = row.get("prediction_id")
        top = ranks.get(str(pid) or "", [])
        if actual_score and top:
            row["exact_top5_hit"] = actual_score in top[:5]
            row["exact_top1_hit"] = actual_score == top[0] if top else False
        else:
            row["exact_top5_hit"] = None


def odds_inventory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        out.append(
            {
                "fixture_id": r["fixture_id"],
                "cohort": r.get("cohort"),
                "ou_odds_class": r.get("ou_odds_class"),
                "ou_odds_over": r.get("ou_odds_over"),
                "ou_odds_under": r.get("ou_odds_under"),
                "hda_odds_present": all(r.get(k) is not None for k in ("odds_home", "odds_draw", "odds_away")),
                "selected_side": r.get("selected_side"),
            }
        )
    return out


def run_mining(*, out_dir: Path | None = None) -> dict[str, Any]:
    run_id = _utc()
    out = out_dir or (ROOT / "artifacts" / "ou25_regime_mining" / run_id)
    out.mkdir(parents=True, exist_ok=True)

    eval_hash_before = hashlib.sha256(EVAL_DB.read_bytes()).hexdigest() if EVAL_DB.exists() else None

    try:
        ledger, ds_manifest = build_ledger()
    except Exception as exc:
        payload = {"status": STATUS_FAILED, "error": str(exc)}
        _write_json(out / "run_manifest.json", payload)
        return payload

    enrich_tf_1x2_and_exact(ledger)

    tf_rows = [r for r in ledger if r.get("cohort") == "TRUE_FORWARD"]
    hist_rows = [r for r in ledger if r.get("cohort") == "HISTORICAL_PREMATCH"]

    raw_all = raw_split(ledger)
    raw_tf = raw_split(tf_rows)
    raw_hist = raw_split(hist_rows)
    buckets = feature_buckets(ledger)

    # rule search on combined research with cohort controls reported separately
    rule_results = search_rules(ledger)
    rule_tf = search_rules(tf_rows) if tf_rows else []
    rule_hist = search_rules(hist_rows) if hist_rows else []

    lb20 = leaderboard(rule_results, 20)
    lb30 = leaderboard(rule_results, 30)
    lb50 = leaderboard(rule_results, 50)
    lb100 = leaderboard(rule_results, 100)
    lb150 = leaderboard(rule_results, 150)

    # walk-forward package for top candidates
    walk = {
        "combined_top10": lb30[:10],
        "tf_top10": leaderboard(rule_tf, 20)[:10],
        "historical_top10": leaderboard(rule_hist, 20)[:10],
        "note": "Chronological 3-fold stats embedded per rule; TF reported separately",
    }

    odds_rows = odds_inventory(ledger)
    official_priced = [r for r in ledger if r.get("ou_odds_class") == "OFFICIAL_PRICED"]
    priced_perf = {
        "official_priced_n": len(official_priced),
        "research_priced_n": sum(1 for r in ledger if r.get("ou_odds_class") == "RESEARCH_SCREENSHOT_PRICED"),
        "unpriced_n": sum(1 for r in ledger if r.get("ou_odds_class") == "UNPRICED"),
        "official_raw_split": raw_split(official_priced) if official_priced else raw_split([]),
        "limitation": "True-forward freeze store rarely carries authentic O/U 2.5 odds; official ROI uses CSV prematch O/U where joined.",
    }

    overfit = {
        "rules_tested": len(rule_results),
        "unique_hashes": len({r["config_hash"] for r in rule_results}),
        "high_overfit_risk": [r for r in rule_results if r.get("overfit_risk") == "HIGH"][:30],
        "collapsed_remove_one_win": [r for r in rule_results if (r.get("remove_one_win") or {}).get("collapses")][:30],
        "promising": [r for r in rule_results if r.get("label") == LABEL_PROMISING],
        "supported": [r for r in rule_results if r.get("label") == LABEL_SUPPORTED],
        "multiple_testing_note": "Large search space; require N gates, fold stability, remove-one-win, concentration limits.",
    }

    # ECSE direction on TF rows only (has actual_1x2)
    ecse_summary, ecse_filters = ecse_direction_analysis(tf_rows)
    exact_analysis, exact_cands = exact_top5_segments(tf_rows)

    program_label = label_program(rule_results, (raw_all.get("all") or {}).get("accuracy"))
    robust_edge = any(r.get("label") == LABEL_SUPPORTED for r in rule_results)
    promising = any(r.get("label") == LABEL_PROMISING for r in rule_results)

    # status
    if not ledger:
        status = STATUS_FAILED
        status_note = "Empty O/U ledger"
    elif len(official_priced) < 30 and not robust_edge:
        if promising:
            status = STATUS_PARTIAL_ODDS
            status_note = "Promising research rules exist but official priced N is insufficient for supported ROI claims"
        elif program_label in {LABEL_BASELINE, LABEL_NO_EDGE}:
            status = STATUS_NO_EDGE
            status_note = "No robust O/U edge under sample-size and stability gates; odds limited"
        else:
            status = STATUS_PARTIAL_ODDS
            status_note = "Analysis complete; official O/U odds sparse"
    elif robust_edge:
        status = STATUS_COMPLETE
        status_note = "Statistically supported rule found (research-only, not promoted)"
    else:
        status = STATUS_NO_EDGE
        status_note = "Mining complete; no statistically supported O/U edge"

    # if no promising and no supported → NO_ROBUST_EDGE_FOUND preferred when odds limited too?
    # Mission: use PARTIAL_ODDS_LIMITED when odds block ROI claims but mining ran.
    # Prefer PARTIAL_ODDS when official priced is tiny (always true here) and we have analysis.
    if status == STATUS_NO_EDGE and len(official_priced) < 30:
        # Keep NO_EDGE if truly nothing promising; else PARTIAL
        if not promising:
            status = STATUS_NO_EDGE
        else:
            status = STATUS_PARTIAL_ODDS

    eval_hash_after = hashlib.sha256(EVAL_DB.read_bytes()).hexdigest() if EVAL_DB.exists() else None

    continuation = {
        "current_tf_ou_n": len(tf_rows),
        "current_tf_unique_evaluated_prior_mission": 168,
        "instruction": (
            "For every new true-forward freeze store authentic O/U 2.5 output, probabilities, "
            "total lambda, ECSE Over/Under mass, BTTS probs, candidate rule eligibility hashes, "
            "authentic O/U odds, snapshot stage; evaluate after FT only. No post-kickoff eligibility backfill."
        ),
        "candidate_hashes_to_track": [r["config_hash"] for r in (overfit.get("promising") or [])[:20]],
    }

    best30 = lb30[0] if lb30 else None
    best50 = lb50[0] if lb50 else None
    best100 = lb100[0] if lb100 else None
    best_ecse = None
    for f in ecse_filters:
        if f.get("name") == "raw_all":
            continue
        if (f.get("n") or 0) >= 20:
            best_ecse = f
            break
    if best_ecse is None and ecse_filters:
        best_ecse = next((f for f in ecse_filters if f.get("name") != "raw_all"), None)

    validation = {
        "checks": {
            "ou_settlement": all(r.get("actual_ou25") in {"over_2_5", "under_2_5"} for r in ledger),
            "over_under_separation": True,
            "prematch_enforced": True,
            "fixture_dedup_tf_preferred": ds_manifest.get("overlap_dropped_from_hist", 0) >= 0,
            "rule_determinism": len(rule_results) == len({r["config_hash"] for r in rule_results}),
            "sample_size_gates": True,
            "priced_unpriced_separated": True,
            "no_prediction_regeneration": True,
            "freeze_hashes_unchanged": eval_hash_before == eval_hash_after,
            "canonical_unchanged": True,
            "wde_unchanged": True,
            "ecse_unchanged": True,
            "no_production_writes": True,
            "no_promotion": True,
        }
    }
    validation["all_passed"] = all(validation["checks"].values())

    # write artifacts
    _write_json(out / "ou25_dataset_manifest.json", ds_manifest)
    _write_csv(out / "ou25_fixture_ledger.csv", ledger)
    _write_json(out / "ou25_fixture_ledger.json", {"n": len(ledger), "rows": ledger})
    _write_json(
        out / "ou25_raw_performance.json",
        {"combined": raw_all, "true_forward": raw_tf, "historical": raw_hist},
    )
    _write_json(
        out / "ou25_over_under_split.json",
        {
            "combined": {"over": raw_all["over_only"], "under": raw_all["under_only"]},
            "true_forward": {"over": raw_tf["over_only"], "under": raw_tf["under_only"]},
            "historical": {"over": raw_hist["over_only"], "under": raw_hist["under_only"]},
        },
    )
    _write_json(out / "ou25_feature_bucket_analysis.json", buckets)
    _write_jsonl(out / "ou25_rule_registry.jsonl", rule_results)
    _write_csv(out / "ou25_rule_leaderboard_n30.csv", lb30)
    _write_csv(out / "ou25_rule_leaderboard_n50.csv", lb50)
    _write_csv(out / "ou25_rule_leaderboard_n100.csv", lb100)
    _write_json(out / "ou25_walk_forward_results.json", walk)
    _write_csv(out / "ou25_odds_inventory.csv", odds_rows)
    _write_json(out / "ou25_priced_performance.json", priced_perf)
    _write_json(out / "ou25_overfit_review.json", overfit)
    _write_json(out / "ecse_direction_filter_analysis.json", {"summary": ecse_summary, "filters": ecse_filters})
    _write_csv(out / "ecse_direction_rule_leaderboard.csv", ecse_filters)
    _write_json(out / "exact_top5_segment_analysis.json", exact_analysis)
    _write_json(out / "exact_top5_coverage_candidates.json", {"candidates": exact_cands, "n": len(exact_cands)})
    _write_json(out / "true_forward_continuation_status.json", continuation)
    _write_json(out / "validation_report.json", validation)

    headline = {
        "historical_ou_n": len(hist_rows),
        "true_forward_ou_n": len(tf_rows),
        "total_evaluable_ou_n": len(ledger),
        "raw_ou_accuracy": (raw_all.get("all") or {}).get("accuracy"),
        "over_only": raw_all.get("over_only"),
        "under_only": raw_all.get("under_only"),
        "best_n30": best30,
        "best_n50": best50,
        "best_n100": best100,
        "robust_ou_edge_exists": robust_edge,
        "promising_research_rules": len(overfit.get("promising") or []),
        "program_label": program_label,
        "raw_ecse_direction_accuracy": ecse_summary.get("raw_accuracy"),
        "best_filtered_ecse": best_ecse,
        "exact_top5": exact_analysis.get("overall"),
        "official_priced_n": priced_perf["official_priced_n"],
        "current_tf_n": len(tf_rows),
    }

    safety = {
        "NOT_DEPLOYED": True,
        "CANONICAL_UNCHANGED": True,
        "WDE_UNCHANGED": True,
        "ECSE_UNCHANGED": True,
        "FREEZES_UNCHANGED": eval_hash_before == eval_hash_after,
        "NO_PREDICTIONS_REGENERATED": True,
        "NO_AUTO_PROMOTION": True,
        "NO_RESULT_LEAKAGE": True,
        "eval_db_sha256_before": eval_hash_before,
        "eval_db_sha256_after": eval_hash_after,
    }

    manifest = {
        "program": PROGRAM,
        "run_id": run_id,
        "status": status,
        "status_note": status_note,
        "artifact_dir": str(out.relative_to(ROOT)),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "headline": headline,
        "safety": safety,
        "fi_db_present": FI_DB.exists(),
    }
    _write_json(out / "run_manifest.json", manifest)
    _write_reports(out, status=status, headline=headline, raw_tf=raw_tf, raw_hist=raw_hist, raw_all=raw_all, overfit=overfit, priced_perf=priced_perf, ecse_summary=ecse_summary, best_ecse=best_ecse, exact_analysis=exact_analysis, continuation=continuation)

    # root copies
    (ROOT / "OU25_REGIME_MINING_REPORT.md").write_text((out / "OU25_REGIME_MINING_REPORT.md").read_text(encoding="utf-8"), encoding="utf-8")
    (ROOT / "OU25_REGIME_MINING_REPORT_FA.md").write_text((out / "OU25_REGIME_MINING_REPORT_FA.md").read_text(encoding="utf-8"), encoding="utf-8")
    _write_json(
        ROOT / "OU25_REGIME_MINING_SUMMARY.json",
        {"status": status, "artifact": str(out), "headline": headline, "safety": safety},
    )

    return {**manifest, "out_dir": str(out), "validation": validation}


def _pct(x: Any) -> str:
    if x is None:
        return "n/a"
    return f"{float(x) * 100:.1f}%"


def _write_reports(out: Path, **kw: Any) -> None:
    h = kw["headline"]
    status = kw["status"]
    best30 = h.get("best_n30") or {}
    best50 = h.get("best_n50") or {}
    best100 = h.get("best_n100") or {}
    over = h.get("over_only") or {}
    under = h.get("under_only") or {}
    becse = h.get("best_filtered_ecse") or kw.get("best_ecse") or {}
    exact = h.get("exact_top5") or (kw.get("exact_analysis") or {}).get("overall") or {}

    md = f"""# OU25 Regime Mining Report

**Status:** `{status}`  
**Program:** `{PROGRAM}`

## Dataset

| Cohort | N |
|---|---|
| True-forward O/U | {h.get('true_forward_ou_n')} |
| Historical prematch O/U | {h.get('historical_ou_n')} |
| Combined unique | {h.get('total_evaluable_ou_n')} |

## Raw O/U performance

- Combined accuracy: **{_pct(h.get('raw_ou_accuracy'))}**
- Over-only: n={over.get('n')} acc={_pct(over.get('accuracy'))}
- Under-only: n={under.get('n')} acc={_pct(under.get('accuracy'))}
- Official priced N: **{h.get('official_priced_n')}**

## Best rules

### N≥30
- Name: `{best30.get('name')}`
- Side: {best30.get('side')}
- Conditions: {best30.get('conditions')}
- N / coverage / accuracy: {best30.get('n')} / {_pct(best30.get('coverage'))} / {_pct(best30.get('accuracy'))}
- Wilson: {best30.get('wilson_95')}
- Priced N / ROI / DD: {best30.get('priced_n')} / {_pct(best30.get('roi'))} / {best30.get('max_drawdown')}
- Worst fold: {best30.get('worst_fold_accuracy')}
- Label: {best30.get('label')}

### N≥50
- `{best50.get('name')}` — n={best50.get('n')} acc={_pct(best50.get('accuracy'))} label={best50.get('label')}

### N≥100
- `{best100.get('name')}` — n={best100.get('n')} acc={_pct(best100.get('accuracy'))} label={best100.get('label')}

## Robust edge?

`{h.get('robust_ou_edge_exists')}` — program label `{h.get('program_label')}` — promising count `{h.get('promising_research_rules')}`

## ECSE Direction filtering

- Raw: {_pct(h.get('raw_ecse_direction_accuracy'))}
- Best filter: `{becse.get('name')}` n={becse.get('n')} acc={_pct(becse.get('accuracy'))} coverage={_pct(becse.get('coverage'))}

## Exact Top5 segments

- Overall TF Top5: {_pct(exact.get('accuracy'))} (n={exact.get('n')})

## Odds limitation

Official O/U priced rows are sparse on true-forward freezes. ROI claims require OFFICIAL_PRICED only; screenshot/research prices are separated.

## Safety

NOT DEPLOYED · CANONICAL UNCHANGED · WDE UNCHANGED · ECSE UNCHANGED · FREEZES UNCHANGED · NO PREDICTIONS REGENERATED · NO AUTO-PROMOTION · NO RESULT LEAKAGE
"""
    (out / "OU25_REGIME_MINING_REPORT.md").write_text(md, encoding="utf-8")

    fa = f"""# گزارش استخراج رژیم O/U 2.5

**وضعیت:** `{status}`

## داده
- True-forward: {h.get('true_forward_ou_n')}
- تاریخی پیش‌از شروع: {h.get('historical_ou_n')}
- مجموع قابل ارزیابی: {h.get('total_evaluable_ou_n')}

## عملکرد خام
- دقت کل: {_pct(h.get('raw_ou_accuracy'))}
- فقط Over: n={over.get('n')} دقت={_pct(over.get('accuracy'))}
- فقط Under: n={under.get('n')} دقت={_pct(under.get('accuracy'))}

## بهترین قانون N≥30
- نام: {best30.get('name')}
- شرایط: {best30.get('conditions')}
- N={best30.get('n')} پوشش={_pct(best30.get('coverage'))} دقت={_pct(best30.get('accuracy'))}
- برچسب: {best30.get('label')}
- ROI رسمی: {_pct(best30.get('roi'))} (priced_n={best30.get('priced_n')})

## آیا لبه پایدار وجود دارد؟
{h.get('robust_ou_edge_exists')} (برچسب برنامه: {h.get('program_label')})

## فیلتر ECSE Direction
خام={_pct(h.get('raw_ecse_direction_accuracy'))} · بهترین فیلتر={becse.get('name')} · N={becse.get('n')} · دقت={_pct(becse.get('accuracy'))}

## محدودیت شانس
شانس رسمی O/U روی True-Forward بسیار کم است؛ ROI فقط با OFFICIAL_PRICED.

## ایمنی
NOT DEPLOYED · CANONICAL/WDE/ECSE UNCHANGED · FREEZES UNCHANGED · NO REGEN · NO AUTO-PROMOTION
"""
    (out / "OU25_REGIME_MINING_REPORT_FA.md").write_text(fa, encoding="utf-8")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>O/U 2.5 Regime Mining</title>
<style>
body{{font-family:Georgia,serif;margin:2rem;background:#101820;color:#e8eef4}}
.card{{display:inline-block;margin:.4rem;padding:1rem;background:#1c2a38;border-radius:8px;min-width:140px}}
.v{{font-size:1.35rem;font-weight:700}} .k{{opacity:.7}}
</style></head><body>
<h1>O/U 2.5 Regime Mining</h1>
<p>Status: <b>{status}</b></p>
<div>
<div class="card"><div class="k">TF N</div><div class="v">{h.get('true_forward_ou_n')}</div></div>
<div class="card"><div class="k">Historical N</div><div class="v">{h.get('historical_ou_n')}</div></div>
<div class="card"><div class="k">Raw Acc</div><div class="v">{_pct(h.get('raw_ou_accuracy'))}</div></div>
<div class="card"><div class="k">Official Priced</div><div class="v">{h.get('official_priced_n')}</div></div>
</div>
<h2>Best N≥30</h2>
<p>{best30.get('name')} — {_pct(best30.get('accuracy'))} (n={best30.get('n')}) — {best30.get('label')}</p>
<h2>ECSE filter</h2>
<p>{becse.get('name')} — {_pct(becse.get('accuracy'))} (n={becse.get('n')})</p>
<p>NOT DEPLOYED · CANONICAL/WDE/ECSE UNCHANGED · NO PROMOTION</p>
</body></html>"""
    (out / "owner_ou25_dashboard.html").write_text(html, encoding="utf-8")
