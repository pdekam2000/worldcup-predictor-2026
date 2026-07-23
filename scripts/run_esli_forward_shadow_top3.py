"""ESLI FORWARD SHADOW runner — read-only candidate selection + Top3 combo.

Consumes the IMMUTABLE canonical multi-day prediction artifact (already frozen by
the canonical pipeline) for 2026-07-23, applies the ESLI shadow layer, selects the
three strongest exact-score fixtures and generates the 27 canonical-Top3 combos.

DOES NOT: regenerate predictions, mutate ECSE/WDE/freezes, or write to any canonical
store. Only writes additive ESLI shadow + daily research artifacts.
"""
from __future__ import annotations
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from esli import shadow, policy  # noqa: E402
from esli.shadow import (assess_fixture, composite, primary_gates_pass,
                         tier_b_gates_pass, top3_scores, top5_scores,
                         generate_27_combos, joint_coverage, registry_record)  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATE = "2026-07-23"
CANON = ROOT / "artifacts/multi_day_predictions/2026-07-22_2026-07-27/20260722T195337Z/full_predictions.json"
DAILY = ROOT / f"artifacts/daily_pipeline/{DATE}/esli_exact_combo"
SHADOW = ROOT / "artifacts/esli_forward_shadow"


def load_day() -> list[dict]:
    d = json.loads(CANON.read_text(encoding="utf-8"))
    return [x for x in d["predictions"] if (x.get("kickoff_vienna") or "").startswith(DATE)]


def main() -> int:
    DAILY.mkdir(parents=True, exist_ok=True)
    SHADOW.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    day = load_day()

    # ---- PART C/D: assessments for every canonical fixture -----------------
    assessments = []
    ranking_rows = []
    for rec in day:
        cls = policy.classify_league(rec.get("competition"))
        a = assess_fixture(rec, DATE)
        score, comps = composite(rec, cls)
        a.composite_score, a.composite_components = score, comps
        assessments.append(a)
        pg_ok, pg_fail = primary_gates_pass(rec)
        tb_ok, tb_fail = tier_b_gates_pass(rec)
        ecse = rec.get("ecse") or {}
        ranking_rows.append({
            "fixture_id": rec["fixture_id"],
            "kickoff_vienna": rec.get("kickoff_vienna"),
            "league": rec.get("competition"),
            "home": rec.get("home_team"), "away": rec.get("away_team"),
            "esli_tier": a.esli_tier, "esli_class": a.eligibility_class,
            "esli_score": a.esli_score, "esli_n": a.sample_size,
            "composite_score": score,
            "consensus": rec.get("consensus"), "no_bet": rec.get("no_bet"),
            "wde_ecse_agree": rec.get("wde_ecse_agreement"),
            "wde_ft_agree": rec.get("wde_ft_agreement"),
            "data_quality": rec.get("data_quality"),
            "top1": ecse.get("top1", {}).get("score"),
            "top1_prob": ecse.get("top1_probability"),
            "top3_mass": ecse.get("top3_mass"), "top5_mass": ecse.get("top5_mass"),
            "entropy": ecse.get("entropy"),
            "bookmaker_count": (rec.get("odds") or {}).get("bookmaker_count"),
            "odds_status": (rec.get("odds") or {}).get("freshness_status"),
            "primary_gates_pass": pg_ok, "primary_gate_fails": ";".join(pg_fail),
            "tier_b_gates_pass": tb_ok, "tier_b_gate_fails": ";".join(tb_fail),
        })

    # ---- PART H/K: build primary candidate pool ---------------------------
    def elig(row):
        if not row["primary_gates_pass"]:
            return False
        if row["esli_class"] == "ESLI_STRONG":
            return True
        if row["esli_class"] == "ESLI_CONDITIONAL":
            return row["tier_b_gates_pass"]
        return False

    candidates = [r for r in ranking_rows if elig(r)]
    candidates.sort(key=lambda r: (-r["composite_score"],))

    # Select 3 by composite score. League diversity is a TIE-BREAKER ONLY:
    # it may reorder candidates whose composite scores are within DIVERSITY_EPS,
    # never override a materially stronger fixture (Part K: "when nearly equal").
    DIVERSITY_EPS = 3.0
    selected: list[dict] = []
    pool = list(candidates)
    while pool and len(selected) < 3:
        best = pool[0]
        used = [s["league"] for s in selected]
        # If best's league already used twice, look for a near-equal diverse alternative.
        if used.count(best["league"]) >= 2:
            alt = next((c for c in pool
                        if c["league"] not in used
                        and (best["composite_score"] - c["composite_score"]) <= DIVERSITY_EPS), None)
            if alt is not None:
                best = alt
        selected.append(best)
        pool.remove(best)

    insufficient = len(selected) < 3
    fixmap = {r["fixture_id"]: r for r in day}

    # ---- PART L: 27 combos -------------------------------------------------
    combos, jc, sel_records = [], {}, []
    if not insufficient:
        sel_records = [fixmap[r["fixture_id"]] for r in selected]
        combos = generate_27_combos(sel_records)
        jc = joint_coverage(sel_records)

    # ---- PART N: rejection table ------------------------------------------
    rejected = []
    for r in ranking_rows:
        if r["fixture_id"] in {s["fixture_id"] for s in selected}:
            continue
        reason = None
        cls = r["esli_class"]
        pgf = r["primary_gate_fails"]
        rec = fixmap[r["fixture_id"]]
        odds_blocked = (rec.get("eligibility") != "PREDICTION_ELIGIBLE"
                        or "odds_not_fresh_complete" in pgf)
        if "not_prematch" in pgf:
            reason = "POST_KICKOFF"
        elif odds_blocked:
            reason = "ODDS_BLOCKED"
        elif cls == "ESLI_AVOID_PRIMARY_EXACT":
            reason = "ESLI_C_OR_D"
        elif cls == "ESLI_PROVISIONAL":
            reason = "PROVISIONAL_SAMPLE"
        elif cls == "ESLI_UNMEASURED":
            reason = "UNMEASURED_LEAGUE"
        elif "high_conflict" in pgf:
            reason = "HIGH_CONFLICT"
        elif cls == "ESLI_CONDITIONAL" and not r["tier_b_gates_pass"]:
            if "top5_mass_below_0.55" in r["tier_b_gate_fails"]:
                reason = "LOW_TOP5_MASS"
            elif "entropy_too_high" in r["tier_b_gate_fails"]:
                reason = "HIGH_ENTROPY"
            else:
                reason = "TIER_B_GATE_FAILED"
        else:
            reason = "NOT_TOP3_COMPOSITE"
        rejected.append({
            "fixture": f'{r["home"]} vs {r["away"]}', "league": r["league"],
            "esli_tier": r["esli_tier"], "esli_class": cls,
            "top5_mass": r["top5_mass"], "composite_score": r["composite_score"],
            "reason_rejected": reason,
        })

    # ================= WRITE ARTIFACTS =====================================
    # PART R: shadow registry + policy
    (SHADOW / "league_registry.json").write_text(json.dumps({
        "registry": registry_record(),
        "generated_at": now,
        "leagues": policy.LEAGUE_EVIDENCE,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (SHADOW / "policy.json").write_text(json.dumps({
        "policy_version": policy.POLICY_VERSION,
        "min_sample": policy.MIN_SAMPLE,
        "composite_weights": policy.COMPOSITE_WEIGHTS,
        "anchors": policy.ANCHORS,
        "tier_b_gates": policy.TIER_B_GATES,
        "classes": ["ESLI_STRONG", "ESLI_CONDITIONAL", "ESLI_AVOID_PRIMARY_EXACT",
                    "ESLI_PROVISIONAL", "ESLI_UNMEASURED"],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    with (SHADOW / "fixture_assessments.jsonl").open("w", encoding="utf-8") as fh:
        for a in assessments:
            d = {k: v for k, v in a.__dict__.items()}
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")

    # selection freezes (links to canonical freeze; ESLI stays separate)
    with (SHADOW / "selection_freezes.jsonl").open("w", encoding="utf-8") as fh:
        for r in selected:
            rec = fixmap[r["fixture_id"]]
            fh.write(json.dumps({
                "fixture_id": r["fixture_id"], "date": DATE,
                "selection_class": "PRIMARY_EXACT_COMBO",
                "esli_tier": r["esli_tier"], "esli_score": r["esli_score"],
                "composite_score": r["composite_score"],
                "linked_canonical_freeze_id": (rec.get("freeze") or {}).get("freeze_id"),
                "linked_canonical_freeze_hash": (rec.get("freeze") or {}).get("content_hash"),
                "canonical_top3": top3_scores(rec),
                "frozen_at": now, "policy_version": policy.POLICY_VERSION,
            }, ensure_ascii=False) + "\n")

    eval_manifest = {
        "model_id": "ESLI-1", "policy_version": policy.POLICY_VERSION,
        "date": DATE, "generated_at": now,
        "selected_fixture_ids": [r["fixture_id"] for r in selected],
        "control_rejected_c_d": [r["fixture_id"] for r in ranking_rows
                                  if r["esli_class"] == "ESLI_AVOID_PRIMARY_EXACT"],
        "evaluation_pending": True, "no_production_promotion": True,
        "thresholds": {"operational_review": 25, "preliminary": 50,
                       "initial_comparison": 100, "promotion_quality": 250, "stronger": 500},
        "evaluate_when_results_available": ["actual_rank", "top1", "top3", "top5", "top10",
                                            "selected_vs_rejected", "sa_perf", "b_perf", "cd_control"],
    }
    (SHADOW / "evaluation_manifest.json").write_text(
        json.dumps(eval_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- daily artifacts --------------------------------------------------
    (DAILY / "discovery.json").write_text(json.dumps({
        "date": DATE, "timezone": "Europe/Vienna", "generated_at": now,
        "total_discovered": len(day),
        "fixtures": [{
            "fixture_id": r["fixture_id"], "kickoff_vienna": r.get("kickoff_vienna"),
            "league": r.get("competition"), "country": r.get("league_country"),
            "home": r.get("home_team"), "away": r.get("away_team"),
            "fixture_status": r.get("fixture_status"),
            "validation_tier": r.get("validation_tier"),
            "prediction_scope": r.get("prediction_scope"),
            "canonical_league_key": r.get("competition"),
            "esli_class": policy.classify_league(r.get("competition"))["eligibility_class"],
            "esli_tier": policy.classify_league(r.get("competition"))["tier"],
            "esli_n": policy.classify_league(r.get("competition"))["n"],
        } for r in day],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    (DAILY / "esli_assessments.json").write_text(json.dumps(
        [a.__dict__ for a in assessments], indent=2, ensure_ascii=False), encoding="utf-8")

    with (DAILY / "candidate_ranking.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ranking_rows[0].keys()))
        w.writeheader()
        for r in sorted(ranking_rows, key=lambda x: -x["composite_score"]):
            w.writerow(r)

    with (DAILY / "rejected_candidates.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rejected[0].keys()))
        w.writeheader()
        w.writerows(sorted(rejected, key=lambda x: -(x["composite_score"] or 0)))

    selected_full = []
    for rank, r in enumerate(selected, start=1):
        rec = fixmap[r["fixture_id"]]
        ecse = rec.get("ecse") or {}
        wde = rec.get("wde") or {}
        selected_full.append({
            "selection_rank": rank, "fixture_id": r["fixture_id"],
            "kickoff_vienna": rec.get("kickoff_vienna"),
            "league": rec.get("competition"), "country": rec.get("league_country"),
            "home": rec.get("home_team"), "away": rec.get("away_team"),
            "esli_tier": r["esli_tier"], "esli_score": r["esli_score"], "esli_n": r["esli_n"],
            "wde_decision": wde.get("decision"),
            "home_prob": wde.get("home_probability"), "draw_prob": wde.get("draw_probability"),
            "away_prob": wde.get("away_probability"), "wde_confidence": wde.get("confidence"),
            "no_bet": rec.get("no_bet"), "consensus": rec.get("consensus"),
            "data_quality": rec.get("data_quality"),
            "top1_5": top5_scores(rec),
            "top3_mass": ecse.get("top3_mass"), "top5_mass": ecse.get("top5_mass"),
            "top10_mass": ecse.get("top10_mass"), "entropy": ecse.get("entropy"),
            "lambda_home": ecse.get("lambda_home"), "lambda_away": ecse.get("lambda_away"),
            "total_lambda": ecse.get("total_lambda"), "ecse_version": ecse.get("model_version"),
            "main_risk": rec.get("main_risk"),
            "selection_class": "PRIMARY_EXACT_COMBO",
            "composite_score": r["composite_score"],
            "composite_components": next(a.composite_components for a in assessments
                                         if a.fixture_id == r["fixture_id"]),
            "linked_canonical_freeze_id": (rec.get("freeze") or {}).get("freeze_id"),
        })
    (DAILY / "selected_top3.json").write_text(json.dumps({
        "date": DATE, "generated_at": now,
        "status": "INSUFFICIENT_QUALIFIED_ESLI_EXACT_FIXTURES" if insufficient else "PRIMARY_EXACT_COMBO_READY",
        "selected": selected_full, "joint_coverage": jc,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    with (DAILY / "exact_score_27_combinations.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["#", "Match A", "Match B", "Match C", "joint_prob_independent"])
        for c in combos:
            w.writerow([c["n"], c["match_a"], c["match_b"], c["match_c"], c["joint_probability_independent"]])

    (DAILY / "evaluation_manifest.json").write_text(
        json.dumps(eval_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- terminal summary -------------------------------------------------
    from collections import Counter
    cls_counts = Counter(r["esli_class"] for r in ranking_rows)
    print("=" * 60)
    print(f"RESOLVED DATE: {DATE}  (Europe/Vienna)")
    print(f"Total discovered fixtures: {len(day)}")
    print(f"Supported prematch (eligible+complete): {sum(1 for r in ranking_rows if r['primary_gates_pass'] or True and fixmap[r['fixture_id']].get('prediction_complete'))}")
    print(f"ESLI classes: {dict(cls_counts)}")
    print(f"Primary candidate pool (gates pass): {len(candidates)}")
    print(f"Selected: {len(selected)}  insufficient={insufficient}")
    for r in selected:
        print(f"  #{selected.index(r)+1} [{r['esli_tier']}] {r['home']} vs {r['away']} "
              f"({r['league']})  comp={r['composite_score']}  top5m={r['top5_mass']:.3f}")
    print(f"27 combos generated: {len(combos)}")
    print(f"Joint coverage: {jc}")
    print(f"Artifacts -> {DAILY}")
    print(f"Shadow    -> {SHADOW}")

    # machine-readable final block for the caller
    print("\n__RESULT__" + json.dumps({
        "insufficient": insufficient,
        "selected": [{"rank": i + 1, "fixture_id": r["fixture_id"],
                      "match": f'{r["home"]} vs {r["away"]}', "league": r["league"],
                      "tier": r["esli_tier"], "composite": r["composite_score"]}
                     for i, r in enumerate(selected)],
        "n_candidates": len(candidates), "n_combos": len(combos),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
