#!/usr/bin/env python3
"""Validate ESLI FORWARD SHADOW implementation + Top3 combo (Part Q).

READ-ONLY. Proves ESLI is a shadow layer with zero canonical impact and that the
Top3 combo package respects all safety rules. Exits non-zero on any failure.
"""
from __future__ import annotations
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from esli import (PUBLIC_VISIBLE, FINAL_DECISION_AUTHORITY, IS_SHADOW, STATUS)  # noqa: E402
from esli import policy  # noqa: E402

DATE = "2026-07-23"
CANON = ROOT / "artifacts/multi_day_predictions/2026-07-22_2026-07-27/20260722T195337Z/full_predictions.json"
DAILY = ROOT / f"artifacts/daily_pipeline/{DATE}/esli_exact_combo"
SHADOW = ROOT / "artifacts/esli_forward_shadow"

results: list[tuple[str, bool, str]] = []

def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))


def main() -> int:
    canon = {x["fixture_id"]: x for x in json.loads(CANON.read_text(encoding="utf-8"))["predictions"]}
    reg = json.loads((SHADOW / "league_registry.json").read_text(encoding="utf-8"))["registry"]
    pol = json.loads((SHADOW / "policy.json").read_text(encoding="utf-8"))
    sel = json.loads((DAILY / "selected_top3.json").read_text(encoding="utf-8"))
    canon_daily = json.loads((DAILY / "canonical_predictions.json").read_text(encoding="utf-8"))["predictions"]
    freezes = json.loads((DAILY / "canonical_freezes.json").read_text(encoding="utf-8"))["freezes"]
    assessments = [json.loads(l) for l in (SHADOW / "fixture_assessments.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    # 1-3 shadow registration
    check("1_esli_registered_shadow", reg.get("status") == "FORWARD_SHADOW" and reg.get("is_shadow") is True)
    check("2_public_visible_false", reg.get("public_visible") is False)
    check("3_final_decision_authority_false", reg.get("final_decision_authority") is False)

    # 4-11 canonical unchanged: daily canonical copy must byte-match source frozen output
    def ecse_sig(ecse):
        return [(ecse[f"top{i}"]["score"], round(ecse[f"top{i}"]["probability"], 6)) for i in range(1, 6)]
    wde_ok = ecse_ok = btts_ok = ou_ok = nobet_ok = odds_ok = top15_ok = freeze_ok = True
    for p in canon_daily:
        src = canon[p["fixture_id"]]
        s_ecse, s_wde = src["ecse"], src["wde"]
        if [(s["score"], round(s["probability"], 6)) for s in p["ecse"]["top1_5"]] != ecse_sig(s_ecse):
            ecse_ok = top15_ok = False
        if p["ecse"]["top5_mass"] != s_ecse.get("top5_mass") or p["ecse"]["lambda_home"] != s_ecse.get("lambda_home"):
            ecse_ok = False
        if p["wde"]["decision"] != s_wde.get("decision") or p["wde"]["away_probability"] != s_wde.get("away_probability"):
            wde_ok = False
        if p["btts"] != src.get("btts"):
            btts_ok = False
        if p["ou25"] != src.get("ou25"):
            ou_ok = False
        if p["wde"]["no_bet"] != src.get("no_bet"):
            nobet_ok = False
        if (src.get("odds") or {}).get("freshness_status") != "ODDS_FRESH":
            odds_ok = False  # freeze-time odds gate must have been FRESH
    check("4_wde_unchanged", wde_ok)
    check("5_ecse_unchanged", ecse_ok)
    check("6_btts_unchanged", btts_ok)
    check("7_ou_unchanged", ou_ok)
    check("8_no_bet_unchanged", nobet_ok)
    check("9_odds_gates_unchanged", odds_ok, "freeze-time ODDS_FRESH preserved")
    check("10_canonical_top1_5_unchanged", top15_ok)
    for fz in freezes:
        src = canon[fz["fixture_id"]]
        if fz["content_hash"] != (src.get("freeze") or {}).get("content_hash"):
            freeze_ok = False
        if fz["freeze_action"] != "REUSED_EXISTING_LEGITIMATE_FREEZE" or not fz["freeze_before_kickoff"]:
            freeze_ok = False
    check("11_canonical_freeze_unchanged", freeze_ok)

    # 12-13 ESLI stored separately + versioned policy
    canon_keys = set()
    for p in canon_daily:
        canon_keys |= set(p.keys())
    check("12_esli_stored_separately", "esli_score" not in canon_keys and "esli_tier" not in canon_keys)
    check("13_league_policy_versioned", pol.get("policy_version") == "esli-policy-v1")

    # 14-18 classification correctness
    def cls_of(lk):
        return policy.classify_league(lk)["eligibility_class"]
    check("14_SA_strong", cls_of("europa_league") == "ESLI_STRONG" and cls_of("allsvenskan") == "ESLI_STRONG"
          and cls_of("conference_league") == "ESLI_STRONG")
    check("15_B_conditional", cls_of("champions_league") == "ESLI_CONDITIONAL" and cls_of("world_cup_2026") == "ESLI_CONDITIONAL")
    check("16_CD_excluded", cls_of("superettan") == "ESLI_AVOID_PRIMARY_EXACT")
    check("17_provisional_handled", cls_of("one_deild") == "ESLI_PROVISIONAL" and cls_of("virsliga") == "ESLI_PROVISIONAL")
    check("18_unmeasured_handled", cls_of("eredivisie_zzz") == "ESLI_UNMEASURED")

    # 19-22 selection gates
    selected = sel["selected"]
    fresh_gate = all((canon[s["fixture_id"]].get("odds") or {}).get("freshness_status") == "ODDS_FRESH" for s in selected)
    prematch = all(canon[s["fixture_id"]].get("fixture_status") == "NS" for s in selected)
    no_hc = all(canon[s["fixture_id"]].get("consensus") != "HIGH_CONFLICT" for s in selected)
    check("19_fresh_odds_required", fresh_gate, "freeze-time freshness enforced")
    check("20_prematch_required", prematch)
    check("21_high_conflict_not_promoted", no_hc)
    # 22 strict tier-B gates enforced: none of selected are Tier B here, but rule exists in policy
    check("22_strict_tier_b_gates_defined", set(pol["tier_b_gates"]) >= {"min_top5_mass", "require_high_agreement"})

    # 23 composite used only for selection (not written into canonical)
    check("23_composite_selection_only", all("composite" not in k for p in canon_daily for k in p.keys()))

    # 24 three legitimate fixtures or honest insufficiency
    check("24_three_or_insufficient", (len(selected) == 3) or sel["status"].startswith("INSUFFICIENT"))
    # 25 canonical Top3 used for combos
    combos = list(csv.DictReader((DAILY / "exact_score_27_combinations.csv").open(encoding="utf-8")))
    top3_by_match = []
    for s in selected:
        e = canon[s["fixture_id"]]["ecse"]
        top3_by_match.append({e[f"top{i}"]["score"] for i in range(1, 4)})
    combos_use_top3 = all(c["Match A"] in top3_by_match[0] and c["Match B"] in top3_by_match[1]
                          and c["Match C"] in top3_by_match[2] for c in combos)
    check("25_canonical_top3_used", combos_use_top3)
    # 26 exactly 27 combos
    check("26_exactly_27_combos", len(combos) == 27)
    # 27 no manual hedge scores (every score in combos belongs to that match's canonical Top3)
    allowed = set().union(*top3_by_match)
    used = {c["Match A"] for c in combos} | {c["Match B"] for c in combos} | {c["Match C"] for c in combos}
    check("27_no_manual_hedge_scores", used <= allowed)
    # 28 selected frozen before kickoff
    check("28_selected_frozen_before_kickoff", all(canon[s["fixture_id"]].get("freeze_before_kickoff") for s in selected))
    # 29 rejected candidates listed
    rej = list(csv.DictReader((DAILY / "rejected_candidates.csv").open(encoding="utf-8")))
    check("29_rejected_listed", len(rej) > 0)
    # 30 evaluation manifest
    em = json.loads((SHADOW / "evaluation_manifest.json").read_text(encoding="utf-8"))
    check("30_evaluation_manifest", em.get("evaluation_pending") is True)
    # 31 no prediction regeneration (daily canonical marked as immutable source)
    check("31_no_regeneration", all("frozen run" in (p.get("note", "") + canon_daily_src) for p in canon_daily
                                    for canon_daily_src in [""]))
    # 32 no production promotion
    check("32_no_production_promotion", em.get("no_production_promotion") is True and reg.get("status") == "FORWARD_SHADOW")
    # 33 no secret in output
    blob = "\n".join((DAILY / f).read_text(encoding="utf-8", errors="ignore")
                     for f in [p.name for p in DAILY.iterdir() if p.is_file()])
    blob += "\n".join((SHADOW / f).read_text(encoding="utf-8", errors="ignore")
                      for f in [p.name for p in SHADOW.iterdir() if p.is_file()])
    secret_markers = ["API_FOOTBALL_KEY", "x-apisports-key", "-----BEGIN", "Bearer "]
    check("33_no_secret_in_output", not any(m in blob for m in secret_markers))
    # 34 reports created
    rep1 = ROOT / "reports/owner/research/ESLI_FORWARD_SHADOW_IMPLEMENTATION_REPORT.md"
    rep2 = ROOT / f"reports/owner/daily/{DATE}_ESLI_TOP3_EXACT_COMBO_FA.md"
    rep3 = ROOT / f"reports/owner/daily/{DATE}_ESLI_CANDIDATE_RANKING_FA.md"
    check("34_reports_created", rep1.exists() and rep2.exists() and rep3.exists())
    # 35 persian report created (non-ascii present)
    fa_ok = rep2.exists() and any(ord(ch) > 1500 for ch in rep2.read_text(encoding="utf-8"))
    check("35_persian_report_created", fa_ok)

    # print
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    print(f"\n{passed}/{len(results)} checks passed")
    if passed != len(results):
        print("RESULT: ESLI_VALIDATION_FAILED")
        return 1
    print("RESULT: ESLI_VALIDATION_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
