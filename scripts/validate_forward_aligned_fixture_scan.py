#!/usr/bin/env python3
"""Validate a forward aligned fixture scan artifact."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.forward_aligned_scan.constants import (
    ARTIFACT_ROOT,
    MAX_DAYS,
    MAX_TIER_A,
    MAX_TIER_B,
    MAX_TIER_S,
    MIN_DAYS,
    TIER_A,
    TIER_B,
    TIER_S,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scan-id", required=True)
    args = p.parse_args(argv)
    d = ROOT / ARTIFACT_ROOT / args.scan_id
    summary_path = d / "summary.json"
    checks: list[tuple[str, bool, str]] = []

    def rec(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    rec("artifact_dir_exists", d.is_dir(), str(d))
    rec("summary_exists", summary_path.is_file())
    if not summary_path.is_file():
        _print(checks)
        return 2
    s = json.loads(summary_path.read_text(encoding="utf-8"))
    rng = ((s.get("discovery") or {}).get("range") or {})
    days = int(rng.get("days") or 0)
    rec("days_in_3_6", MIN_DAYS <= days <= MAX_DAYS, str(days))
    rec("scan_id_match", s.get("scan_id") == args.scan_id)
    rec("research_only", s.get("research_only") is True)
    rec("no_official_freeze", s.get("official_freeze_created") is False)
    zw = s.get("zero_write_integrity") or {}
    rec("zero_write_ok", zw.get("ok") is True, zw.get("proof_text", ""))
    rec("writes_completed_zero", int(zw.get("canonical_writes_completed") or 0) == 0)
    rec("freeze_created_false", zw.get("freeze_created") is False)
    rec("wsp_written_false", zw.get("wsp_written") is False)
    rec("ecse_canonical_written_false", zw.get("ecse_canonical_written") is False)

    sel = s.get("selection") or {}
    rec("tier_s_cap", len(sel.get("tier_s") or []) <= MAX_TIER_S)
    rec("tier_a_cap", len(sel.get("tier_a") or []) <= MAX_TIER_A)
    rec("tier_b_cap", len(sel.get("tier_b") or []) <= MAX_TIER_B)
    rec("no_quota_fill", sel.get("no_quota_fill") is True)

    # Tier S invariants
    for r in sel.get("tier_s") or []:
        dirs = r.get("directions") or {}
        pred = r.get("prediction") or {}
        ok = (
            dirs.get("wde_decision") == dirs.get("ecse_top5_majority")
            and dirs.get("wde_decision") == dirs.get("ecse_top1_direction")
            and pred.get("no_bet") is False
            and str(pred.get("consensus") or "").upper() == "HIGH_AGREEMENT"
            and r.get("alignment_tier") == TIER_S
        )
        rec(f"tier_s_invariant_{r.get('fixture_id')}", ok)

    # Rejected must not appear in selected S/A
    selected_ids = {int(r["fixture_id"]) for bucket in ("tier_s", "tier_a") for r in (sel.get(bucket) or [])}
    for r in sel.get("rejected") or []:
        if "WDE_ECSE_TOP5_MAJORITY_CONFLICT" in (r.get("reject_reasons") or []):
            rec(f"conflict_not_selected_{r.get('fixture_id')}", int(r["fixture_id"]) not in selected_ids)

    # Top1-Top5 formatting home-away + probability persistence for selected
    for bucket in ("tier_s", "tier_a", "tier_b"):
        for r in sel.get(bucket) or []:
            ranks = (r.get("directions") or {}).get("ranks") or []
            ecse = (r.get("prediction") or {}).get("ecse") or {}
            for row in ranks:
                sc = str(row.get("score") or "")
                rec(f"score_format_{r.get('fixture_id')}_{sc}", ("-" in sc and sc.count("-") == 1) or sc == "")
            # New scans should persist probabilities (skip if scan predates fix and mass null)
            if s.get("probabilities_persisted_all_predicted") is True or ecse.get("top5_mass") is not None:
                for i in range(1, 6):
                    t = ecse.get(f"top{i}") or {}
                    if isinstance(t, dict) and t.get("score"):
                        rec(
                            f"prob_persisted_{r.get('fixture_id')}_top{i}",
                            isinstance(t.get("probability"), (int, float)) and float(t["probability"]) > 0,
                        )
                rec(
                    f"mass_persisted_{r.get('fixture_id')}",
                    ecse.get("top5_mass") is not None and ecse.get("top3_mass") is not None,
                )
                rec(f"entropy_persisted_{r.get('fixture_id')}", ecse.get("entropy") is not None)
            if bucket in ("tier_s", "tier_a") and r.get("hours_to_kickoff") is not None:
                rec(f"not_started_{r.get('fixture_id')}", float(r["hours_to_kickoff"]) > 0)
            if bucket == "tier_a":
                rec(
                    f"tier_a_has_s_failure_{r.get('fixture_id')}",
                    bool(r.get("tier_s_failure_reasons")) or ecse.get("top5_mass") is None,
                )
            if bucket == "tier_s":
                mass = ecse.get("top5_mass")
                rec(
                    f"tier_s_mass_gate_{r.get('fixture_id')}",
                    mass is not None and float(mass) >= 0.52,
                )

            # Reason-based no_bet checks (new scans that expose recompute fields only).
            if pred.get("no_bet_recomputed") is True or pred.get("no_bet_decision_stage"):
                reasons = pred.get("no_bet_reasons")
                if reasons is None:
                    reasons = (pred.get("no_bet_diagnostics") or {}).get("no_bet_reasons") or []
                if not isinstance(reasons, list):
                    reasons = [reasons] if reasons else []
                fid = r.get("fixture_id")
                rec(f"no_bet_reasons_list_{fid}", isinstance(reasons, list))
                if pred.get("no_bet") is True:
                    rec(f"no_bet_true_has_reason_{fid}", len(reasons) >= 1)
                if pred.get("no_bet") is False:
                    rec(f"no_bet_false_zero_reasons_{fid}", len(reasons) == 0)
                stage = pred.get("no_bet_decision_stage") or (pred.get("no_bet_diagnostics") or {}).get(
                    "no_bet_decision_stage"
                )
                rec(
                    f"no_bet_post_enrichment_{fid}",
                    stage in (None, "FINAL_POST_ENRICHMENT") or stage == "FINAL_POST_ENRICHMENT",
                )
                # Deterministic ordering: sorted by canonical order equals list if non-empty
                if len(reasons) >= 2:
                    from worldcup_predictor.decision.no_bet_reasons import (
                        NoBetReason,
                        ordered_reason_codes,
                    )

                    try:
                        enums = [NoBetReason(x) for x in reasons]
                        rec(
                            f"no_bet_reason_order_{fid}",
                            reasons == ordered_reason_codes(enums),
                        )
                    except Exception:
                        rec(f"no_bet_reason_order_{fid}", False, "non-canonical reason code")

    # No duplicate selected fixtures
    all_sel = []
    for bucket in ("tier_s", "tier_a", "tier_b"):
        all_sel.extend(int(r["fixture_id"]) for r in (sel.get(bucket) or []))
    rec("no_duplicate_selected", len(all_sel) == len(set(all_sel)))

    rec("exclusion_audit_exists", (d / "exclusion_audit.json").is_file())
    rec("fixtures_csv_exists", (d / "fixtures.csv").is_file())
    if (d / "baseline_comparison.json").is_file():
        rec("baseline_comparison_present", True)

    _print(checks)
    failed = sum(1 for _, ok, _ in checks if not ok)
    return 0 if failed == 0 else 2


def _print(checks: list[tuple[str, bool, str]]) -> None:
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        extra = f" — {detail}" if detail else ""
        print(f"[{mark}] {name}{extra}")
    print(f"TOTAL={len(checks)} FAILED={sum(1 for _, ok, _ in checks if not ok)}")


if __name__ == "__main__":
    raise SystemExit(main())
