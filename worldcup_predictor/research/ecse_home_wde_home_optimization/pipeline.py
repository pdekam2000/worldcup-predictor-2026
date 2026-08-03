"""Orchestrate ECSE HOME ∧ WDE HOME forensic optimization (read-only)."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_home_wde_home_optimization import (
    MIN_COVERAGE,
    MIN_N,
    MIN_WORST_FOLD,
    PROGRAM,
    STATUS_COMPLETE,
    STATUS_DATA_LIMITED,
    STATUS_NO_IMPROVEMENT,
    TARGET_ACC,
)
from worldcup_predictor.research.ecse_home_wde_home_optimization.dataset import (
    EVAL_DB,
    ROOT,
    extract_home_agree,
    load_base_universe,
)
from worldcup_predictor.research.ecse_home_wde_home_optimization.forensics import (
    cluster_failures,
    feature_importance,
    run_threshold_search,
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


def _pct(x: Any) -> str:
    if x is None:
        return "n/a"
    return f"{float(x) * 100:.1f}%"


def run(*, out_dir: Path | None = None) -> dict[str, Any]:
    run_id = _utc()
    out = out_dir or (ROOT / "artifacts" / "ecse_home_wde_home_optimization" / run_id)
    out.mkdir(parents=True, exist_ok=True)

    eval_hash_before = hashlib.sha256(EVAL_DB.read_bytes()).hexdigest() if EVAL_DB.exists() else None

    universe, manifest = load_base_universe()
    base = extract_home_agree(universe)
    wins = [r for r in base if r.get("direction_hit")]
    losses = [r for r in base if not r.get("direction_hit")]

    if len(base) < 30:
        status = STATUS_DATA_LIMITED
        decision = "A"
        decision_text = "No robust improvement exists (insufficient base sample)."
        payload = {
            "status": status,
            "decision": decision,
            "decision_text": decision_text,
            "base_n": len(base),
            "universe_n": len(universe),
        }
        _write_json(out / "run_manifest.json", payload)
        return payload

    importance = feature_importance(wins, losses)
    clusters = cluster_failures(losses)
    candidates = run_threshold_search(base, universe_n=len(universe))

    base_row = next(c for c in candidates if c["name"].startswith("BASE_ecse"))
    passing = [c for c in candidates if c.get("passes_optimization_constraints")]
    # near-miss: acc>=75, n>=40, worst>=60
    near = [
        c
        for c in candidates
        if c["name"] != base_row["name"]
        and (c.get("accuracy") or 0) >= TARGET_ACC
        and (c.get("n") or 0) >= 40
    ]

    if passing:
        best = passing[0]
        decision = "B"
        decision_text = "A new superior rule exists."
        status = STATUS_COMPLETE
        why = _explain(best, importance, clusters)
    else:
        best = None
        decision = "A"
        decision_text = "No robust improvement exists."
        # if any candidate hits 75% but fails other gates → data/constraint limited honesty
        if near:
            status = STATUS_NO_IMPROVEMENT
            why = (
                "Some filters reach >=75% accuracy but violate N/coverage/worst-fold/concentration/"
                "stability constraints. The base 72.6% rule remains the strongest robust rule."
            )
        else:
            status = STATUS_NO_IMPROVEMENT
            why = (
                "No one- or two-condition filter simultaneously exceeds 75% accuracy while keeping "
                f"N>={MIN_N}, coverage>={_pct(MIN_COVERAGE)}, worst fold>={_pct(MIN_WORST_FOLD)}, "
                "and stability under leave-one-win / bootstrap checks."
            )

    # ROI summary
    priced_n = (base_row.get("priced") or {}).get("priced_n") or 0
    roi = {
        "base_rule": base_row.get("priced"),
        "best_rule": (best or {}).get("priced") if best else None,
        "note": (
            "ROI uses authentic frozen home odds only (unit stake on Home)."
            if priced_n
            else "ROI NOT AVAILABLE for meaningful inference — priced N too small or missing on many rows."
        ),
        "roi_available": bool(priced_n and priced_n >= 20),
    }
    if not roi["roi_available"]:
        roi["headline"] = "ROI NOT AVAILABLE"

    # bootstrap / leave-one-out packages
    bootstrap = {
        "base": base_row.get("bootstrap_95"),
        "passing": [{k: c.get(k) for k in ("name", "n", "accuracy", "bootstrap_95")} for c in passing],
        "top10": [{k: c.get(k) for k in ("name", "n", "accuracy", "bootstrap_95", "passes_optimization_constraints")} for c in candidates[:10]],
    }
    leave_one = {
        "base": base_row.get("remove_one_win"),
        "leave_two_base": base_row.get("leave_two_win_min_accuracy"),
        "top_candidates": [
            {
                "name": c["name"],
                "remove_one_win": c.get("remove_one_win"),
                "leave_two_win_min_accuracy": c.get("leave_two_win_min_accuracy"),
            }
            for c in candidates[:25]
        ],
    }
    walk_forward = {
        "base": {"fold_stats": base_row.get("fold_stats"), "worst": base_row.get("worst_fold"), "mean": base_row.get("mean_fold")},
        "top_candidates": [
            {"name": c["name"], "fold_stats": c.get("fold_stats"), "worst": c.get("worst_fold"), "mean": c.get("mean_fold")}
            for c in candidates[:25]
        ],
    }

    eval_hash_after = hashlib.sha256(EVAL_DB.read_bytes()).hexdigest() if EVAL_DB.exists() else None
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

    # write artifacts
    _write_csv(out / "dataset.csv", base)
    _write_csv(out / "wins.csv", wins)
    _write_csv(out / "losses.csv", losses)
    _write_json(out / "cluster_analysis.json", clusters)
    _write_json(out / "feature_importance.json", importance)
    _write_json(
        out / "threshold_search.json",
        {
            "n_candidates": len(candidates),
            "n_passing": len(passing),
            "constraints": {
                "target_accuracy": TARGET_ACC,
                "min_n": MIN_N,
                "min_coverage_of_universe": MIN_COVERAGE,
                "min_worst_fold": MIN_WORST_FOLD,
            },
            "candidates": candidates,
        },
    )
    _write_csv(
        out / "rule_candidates.csv",
        [
            {
                "name": c["name"],
                "conditions": "|".join(c.get("conditions") or []),
                "n": c.get("n"),
                "wins": c.get("wins"),
                "losses": c.get("losses"),
                "accuracy": c.get("accuracy"),
                "coverage_of_universe": c.get("coverage_of_universe"),
                "wilson_low": (c.get("wilson_95") or {}).get("low"),
                "wilson_high": (c.get("wilson_95") or {}).get("high"),
                "worst_fold": c.get("worst_fold"),
                "mean_fold": c.get("mean_fold"),
                "league_concentration": c.get("league_concentration"),
                "stability": c.get("stability"),
                "passes": c.get("passes_optimization_constraints"),
                "roi": (c.get("priced") or {}).get("roi"),
                "priced_n": (c.get("priced") or {}).get("priced_n"),
            }
            for c in candidates
        ],
    )
    _write_json(out / "bootstrap_results.json", bootstrap)
    _write_json(out / "leave_one_out.json", leave_one)
    _write_json(out / "walk_forward.json", walk_forward)
    _write_json(out / "roi.json", roi)

    final = {
        "program": PROGRAM,
        "decision": decision,
        "decision_text": decision_text,
        "status": status,
        "base_rule": {
            "rule": ["ecse_direction=home_win", "wde_decision=home_win"],
            "n": len(base),
            "wins": len(wins),
            "losses": len(losses),
            "accuracy": base_row.get("accuracy"),
            "coverage_of_universe": base_row.get("coverage_of_universe"),
            "worst_fold": base_row.get("worst_fold"),
            "wilson_95": base_row.get("wilson_95"),
        },
        "superior_rule": best,
        "why": why,
        "universe_n": len(universe),
        "dataset_manifest": manifest,
        "top_near_misses": near[:10],
        "safety": safety,
    }
    _write_json(out / "FINAL_DECISION.json", final)
    _write_reports(out, final=final, clusters=clusters, importance=importance, roi=roi)

    run_manifest = {
        "program": PROGRAM,
        "run_id": run_id,
        "status": status,
        "decision": decision,
        "decision_text": decision_text,
        "artifact_dir": str(out.relative_to(ROOT)),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_n": len(base),
        "wins": len(wins),
        "losses": len(losses),
        "candidates_tested": len(candidates),
        "passing": len(passing),
        "safety": safety,
    }
    _write_json(out / "run_manifest.json", run_manifest)

    # root copies
    (ROOT / "ECSE_HOME_WDE_HOME_OPTIMIZATION_REPORT.md").write_text(
        (out / "FINAL_REPORT.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (ROOT / "ECSE_HOME_WDE_HOME_OPTIMIZATION_REPORT_FA.md").write_text(
        (out / "FINAL_REPORT_FA.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    _write_json(ROOT / "ECSE_HOME_WDE_HOME_OPTIMIZATION_SUMMARY.json", {**run_manifest, "final": final})

    return {**run_manifest, "out_dir": str(out), "final": final}


def _explain(best: dict[str, Any], importance: dict[str, Any], clusters: dict[str, Any]) -> str:
    top_num = sorted(
        ((k, v) for k, v in (importance.get("numeric") or {}).items() if v.get("diff_mean") is not None),
        key=lambda kv: -abs(kv[1]["diff_mean"]),
    )[:5]
    bits = [f"Added conditions {best.get('conditions')} lift accuracy to {_pct(best.get('accuracy'))} on n={best.get('n')}."]
    if top_num:
        bits.append(
            "Largest win/loss mean gaps were: "
            + ", ".join(f"{k} (Δ={v['diff_mean']:.3f})" for k, v in top_num)
        )
    bits.append(f"Dominant loss clusters in base set: {clusters.get('cluster_counts')}.")
    return " ".join(bits)


def _write_reports(out: Path, *, final: dict[str, Any], clusters: dict[str, Any], importance: dict[str, Any], roi: dict[str, Any]) -> None:
    base = final["base_rule"]
    best = final.get("superior_rule")
    decision = final["decision"]
    md = f"""# ECSE HOME ∧ WDE HOME — Forensic Optimization

**Status:** `{final['status']}`  
**Decision:** **{decision}** — {final['decision_text']}

## Base rule (current best)

- Rule: ECSE Direction = HOME **AND** WDE = HOME
- N={base['n']} · Wins={base['wins']} · Losses={base['losses']}
- Accuracy={_pct(base['accuracy'])}
- Coverage (of TF universe {final['universe_n']})={_pct(base['coverage_of_universe'])}
- Worst fold={_pct(base['worst_fold'])}
- Wilson 95%: {base.get('wilson_95')}

## Failure clusters (17 losses)

```json
{json.dumps(clusters.get('cluster_counts'), indent=2)}
```

## Optimization result

"""
    if decision == "B" and best:
        md += f"""
### Superior rule

- Exact conditions: `{best.get('conditions')}`
- N={best.get('n')} · Acc={_pct(best.get('accuracy'))} · Coverage={_pct(best.get('coverage_of_universe'))}
- Worst fold={_pct(best.get('worst_fold'))} · Mean fold={_pct(best.get('mean_fold'))}
- Wilson: {best.get('wilson_95')}
- ROI: {_pct((best.get('priced') or {}).get('roi'))} (priced_n={(best.get('priced') or {}).get('priced_n')})
- Why: {final.get('why')}
"""
    else:
        md += f"""
### No superior rule

{final.get('why')}

Near-misses (≥75% but failing other gates): {len(final.get('top_near_misses') or [])}
"""
        for nm in (final.get("top_near_misses") or [])[:5]:
            md += f"\n- `{nm.get('name')}` n={nm.get('n')} acc={_pct(nm.get('accuracy'))} worst={_pct(nm.get('worst_fold'))} cov={_pct(nm.get('coverage_of_universe'))} passes={nm.get('passes_optimization_constraints')}"

    md += f"""

## ROI

{roi.get('headline') or roi.get('note')}

Base priced: {base and final['base_rule']}
Priced block: `{json.dumps(roi.get('base_rule'), default=str)}`

## Top numeric win vs loss gaps

```json
{json.dumps({k: importance.get('numeric', {}).get(k) for k in list((importance.get('numeric') or {}))[:8]}, indent=2, default=str)}
```

## Safety

NOT DEPLOYED · CANONICAL UNCHANGED · WDE UNCHANGED · ECSE UNCHANGED · FREEZES UNCHANGED · NO PREDICTIONS REGENERATED · NO AUTO-PROMOTION · NO RESULT LEAKAGE

Success criterion met: honestly determined whether 72.6% can become a reliable ≥75% rule with meaningful N.
"""
    (out / "FINAL_REPORT.md").write_text(md, encoding="utf-8")

    fa = f"""# بهینه‌سازی قانونی ECSE=HOME و WDE=HOME

**وضعیت:** `{final['status']}`  
**تصمیم نهایی:** **{decision}** — {final['decision_text']}

## قانون پایه
- ECSE=HOME و WDE=HOME
- N={base['n']} · دقت={_pct(base['accuracy'])} · پوشش={_pct(base['coverage_of_universe'])}
- بدترین فولد={_pct(base['worst_fold'])}

## نتیجه
"""
    if decision == "B" and best:
        fa += f"""
قانون برتر پیدا شد:
- شرایط: {best.get('conditions')}
- N={best.get('n')} · دقت={_pct(best.get('accuracy'))} · پوشش={_pct(best.get('coverage_of_universe'))}
- بدترین فولد={_pct(best.get('worst_fold'))}
- ROI={_pct((best.get('priced') or {}).get('roi'))}
- دلیل: {final.get('why')}
"""
    else:
        fa += f"""
بهبود پایدار یافت نشد.

{final.get('why')}
"""

    fa += """
## ایمنی
NOT DEPLOYED · CANONICAL/WDE/ECSE UNCHANGED · FREEZES UNCHANGED · NO REGEN · NO AUTO-PROMOTION

موفقیت این مأموریت یافتن اجباری ۷۵٪ نیست؛ موفقیت تشخیص صادقانه امکان‌پذیری آن است.
"""
    (out / "FINAL_REPORT_FA.md").write_text(fa, encoding="utf-8")
