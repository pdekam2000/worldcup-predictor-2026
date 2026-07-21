#!/usr/bin/env python3
"""Read-only shadow replay of no_bet reason recompute on FAS forensic baseline.

Uses immutable scan + forensic audit inputs only — no prediction regeneration,
no odds refresh, no canonical writes.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup_predictor.decision.no_bet_evaluator import evaluate_no_bet_reasons
from worldcup_predictor.decision.no_bet_reasons import NoBetReason

SCAN_ID = "fas_2026-07-21_6d_20260721T072524Z_8469733f"
FORENSIC_PATH = ROOT / "reports" / "research" / "no_bet_forensic_audit.json"
STICKY_IDS = {
    1495743,
    1495744,
    1508815,
    1593477,
    1556390,
    1494219,
    1556392,
    1593521,
}
REFRESH_CANDIDATES = {1595191, 1508817, 1495740, 1556391, 1593479, 1591936}


def _category(fx: dict, decision) -> str:
    fid = int(fx["fixture_id"])
    old = bool(fx["no_bet"])
    new = bool(decision.no_bet)
    conf = float(fx["observed_confidence"])
    code = fx.get("primary_blocker_code") or ""

    if old and new and NoBetReason.CONFIDENCE_BELOW_60.value in decision.active_reasons:
        return "UNCHANGED_VALID_BLOCK"
    if old and new and decision.active_reasons:
        if NoBetReason.LEGACY_UNKNOWN_REASON.value in decision.active_reasons:
            return "LEGACY_REASON_REQUIRES_REVIEW"
        if code == "STICKY_NO_BET_FLAG_AFTER_CONF_CLEAR":
            # Should have cleared — unexpected retention
            return "UNEXPECTED_CHANGE"
        return "RETAINED_NON_CONFIDENCE_BLOCK"
    if old and not new:
        if code == "STICKY_NO_BET_FLAG_AFTER_CONF_CLEAR" or fid in STICKY_IDS:
            return "CLEARED_STICKY_INHERITANCE"
        if NoBetReason.CONFIDENCE_BELOW_60.value in decision.cleared_reasons:
            return "CLEARED_CONFIDENCE_BLOCK"
        return "UNEXPECTED_CHANGE"
    if not old and not new:
        return "UNCHANGED_VALID_BLOCK"
    if not old and new:
        return "UNEXPECTED_CHANGE"
    return "UNEXPECTED_CHANGE"


def _shadow_tier(fx: dict, new_no_bet: bool) -> str:
    """Shadow tier estimate: only flip no_bet gate; do not invent other gates."""
    old_tier = fx.get("tier") or ""
    if new_no_bet:
        return old_tier  # still blocked on no_bet → same Tier A/B
    # Cleared no_bet: still Tier A unless all other Tier S gates already known pass.
    # Forensic cohort is one-gate-no_bet-only → shadow promote to Tier S candidate.
    if old_tier.startswith("A_") and not new_no_bet:
        return "S_FULL_ALIGNMENT_SHADOW"
    return old_tier


def main() -> int:
    forensic = json.loads(FORENSIC_PATH.read_text(encoding="utf-8"))
    fixtures = forensic["fixtures"]
    assert len(fixtures) == 23, f"expected 23 one-gate fixtures, got {len(fixtures)}"

    run_id = f"nbet_shadow_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    art_dir = ROOT / "artifacts" / "research" / "no_bet_recompute" / run_id
    art_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    categories: dict[str, int] = {}
    unexpected = []
    sticky_table = []
    conf_cohort = []

    for fx in fixtures:
        fid = int(fx["fixture_id"])
        conf = float(fx["observed_confidence"])
        dq = float(fx["observed_data_quality"])
        old_no_bet = bool(fx["no_bet"])
        primary = fx.get("primary_blocker_code") or ""

        # Reconstruct baseline reasons from forensic classification only — never invent.
        inherited: list[str] = []
        if primary == "CONFIDENCE_BELOW_60" or conf < 60.0:
            inherited.append(NoBetReason.CONFIDENCE_BELOW_60.value)
        # Sticky cohort: boolean only — no inherited reason codes (the bug).
        # Do NOT invent LEGACY_UNKNOWN for sticky-only; sticky boolean is not a reason.

        decision = evaluate_no_bet_reasons(
            confidence=conf,
            wde_data_quality=dq,
            visibility_data_quality=dq,
            scoring_data_quality=dq,
            odds_status="fresh",  # scan already required fresh odds for prediction
            placeholder=False,
            inherited_reasons=inherited,
            baseline_no_bet=old_no_bet,
        )
        cat = _category(fx, decision)
        categories[cat] = categories.get(cat, 0) + 1
        if cat == "UNEXPECTED_CHANGE":
            unexpected.append(fid)

        shadow_tier = _shadow_tier(fx, decision.no_bet)
        row = {
            "fixture_id": fid,
            "fixture_name": fx.get("fixture_name"),
            "old_no_bet": old_no_bet,
            "new_no_bet": decision.no_bet,
            "old_reasons": fx.get("exposed_no_bet_reasons") or [],
            "reconstructed_baseline_reasons": inherited,
            "final_active_reasons": decision.active_reasons,
            "cleared_reasons": decision.cleared_reasons,
            "retained_reasons": decision.retained_reasons,
            "confidence": conf,
            "wde_data_quality": dq,
            "visibility_data_quality": dq,
            "scoring_data_quality": dq,
            "old_tier": fx.get("tier"),
            "shadow_new_tier": shadow_tier,
            "category": cat,
            "primary_blocker_code": primary,
            "refresh_candidate": fid in REFRESH_CANDIDATES,
            "sticky_cohort": fid in STICKY_IDS,
            "expected_change": (
                (fid in STICKY_IDS and old_no_bet and not decision.no_bet)
                or (primary == "CONFIDENCE_BELOW_60" and decision.no_bet)
            ),
        }
        rows.append(row)

        if fid in STICKY_IDS:
            sticky_table.append(
                {
                    "fixture_id": fid,
                    "fixture_name": fx.get("fixture_name"),
                    "old_no_bet": old_no_bet,
                    "final_conf": conf,
                    "wde_dq": dq,
                    "other_active_reasons": decision.active_reasons,
                    "new_no_bet": decision.no_bet,
                    "shadow_tier": shadow_tier,
                    "verdict": (
                        "confirmed_bug_cleared"
                        if not decision.no_bet
                        else (
                            "still_legitimately_blocked"
                            if decision.active_reasons
                            else "unknown_missing_trace"
                        )
                    ),
                }
            )

        if conf < 60.0 or primary == "CONFIDENCE_BELOW_60":
            conf_cohort.append(
                {
                    "fixture_id": fid,
                    "confidence": conf,
                    "still_blocked": decision.no_bet,
                    "active_reasons": decision.active_reasons,
                    "refresh_candidate": fid in REFRESH_CANDIDATES,
                    "note": (
                        "remains blocked — final confidence still below 60; "
                        "refresh candidates may clear only after fresh prediction"
                        if decision.no_bet
                        else "UNEXPECTED clear while conf<60"
                    ),
                }
            )

    # Artifacts
    csv_path = art_dir / "fixture_comparison.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "fixture_id",
                "fixture_name",
                "old_no_bet",
                "new_no_bet",
                "confidence",
                "wde_data_quality",
                "category",
                "old_tier",
                "shadow_new_tier",
                "final_active_reasons",
                "cleared_reasons",
            ],
        )
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    **{k: r[k] for k in w.fieldnames if k in r},
                    "final_active_reasons": "|".join(r["final_active_reasons"]),
                    "cleared_reasons": "|".join(r["cleared_reasons"]),
                }
            )

    transitions = {
        "scan_id": SCAN_ID,
        "run_id": run_id,
        "categories": categories,
        "unexpected_fixture_ids": unexpected,
        "rows": rows,
    }
    (art_dir / "reason_transitions.json").write_text(
        json.dumps(transitions, indent=2), encoding="utf-8"
    )

    tier_transitions = {
        "promotions_to_shadow_tier_s": [
            r["fixture_id"] for r in rows if r["shadow_new_tier"] == "S_FULL_ALIGNMENT_SHADOW"
        ],
        "unchanged_tiers": [
            r["fixture_id"] for r in rows if r["old_tier"] == r["shadow_new_tier"]
        ],
    }
    (art_dir / "tier_transitions.json").write_text(
        json.dumps(tier_transitions, indent=2), encoding="utf-8"
    )

    zero_write = {
        "canonical_writes": 0,
        "freeze_mutated": False,
        "historical_rows_rewritten": False,
        "scan_artifacts_mutated": False,
        "prediction_regenerated": False,
        "odds_refreshed": False,
        "mode": "READ_ONLY_SHADOW_REPLAY",
    }
    (art_dir / "zero_write_integrity.json").write_text(
        json.dumps(zero_write, indent=2), encoding="utf-8"
    )

    promotion_proofs = []
    for r in rows:
        if r["shadow_new_tier"] == "S_FULL_ALIGNMENT_SHADOW":
            promotion_proofs.append(
                {
                    "fixture_id": r["fixture_id"],
                    "proof": {
                        "old_no_bet": True,
                        "new_no_bet": False,
                        "active_reasons_empty": r["final_active_reasons"] == [],
                        "confidence_gte_60": r["confidence"] >= 60.0,
                        "wde_dq_gte_50": r["wde_data_quality"] >= 50.0,
                        "visibility_dq_gte_45": r["visibility_data_quality"] >= 45.0,
                        "scoring_dq_gte_45": r["scoring_data_quality"] >= 45.0,
                        "cleared_sticky_only": r["category"] == "CLEARED_STICKY_INHERITANCE",
                        "other_tier_s_gates": "ASSUMED_FROM_ONE_GATE_FORENSIC_COHORT",
                        "note": (
                            "Shadow promotion assumes forensic one-gate cohort "
                            "(only no_bet blocked Tier S). Live Tier S still requires "
                            "fresh odds + all alignment gates on a new scan."
                        ),
                    },
                }
            )
    (art_dir / "promotion_proofs.json").write_text(
        json.dumps(promotion_proofs, indent=2), encoding="utf-8"
    )

    status = (
        "NO_BET_SHADOW_REPLAY_PASS"
        if not unexpected
        else "NO_BET_SHADOW_REPLAY_UNEXPECTED_CHANGE"
    )

    report = {
        "status": status,
        "scan_id": SCAN_ID,
        "run_id": run_id,
        "fixture_count": len(rows),
        "categories": categories,
        "unexpected_changes": unexpected,
        "sticky_fixtures": sticky_table,
        "confidence_cohort": conf_cohort,
        "shadow_tier_s_promotions": tier_transitions["promotions_to_shadow_tier_s"],
        "thresholds_unchanged": {
            "confidence": 60.0,
            "wde_dq": 50.0,
            "visibility_dq": 45.0,
            "scoring_dq": 45.0,
        },
        "zero_write": zero_write,
        "artifact_dir": str(art_dir.relative_to(ROOT)).replace("\\", "/"),
    }

    (ROOT / "reports" / "research" / "no_bet_shadow_replay.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    # Markdown reports
    md_lines = [
        "# NO_BET Shadow Replay",
        "",
        f"**Status:** `{status}`",
        f"**Scan:** `{SCAN_ID}`",
        f"**Run:** `{run_id}`",
        f"**Fixtures:** {len(rows)} (one-gate Tier A cohort)",
        "",
        "## Categories",
        "",
    ]
    for k, v in sorted(categories.items()):
        md_lines.append(f"- `{k}`: **{v}**")
    md_lines += [
        "",
        f"## Unexpected changes",
        "",
        f"{unexpected if unexpected else '_None_'}",
        "",
        "## Sticky cohort (8)",
        "",
        "| Fixture | Old no_bet | Final conf | WDE DQ | Other active reasons | New no_bet | Shadow tier | Verdict |",
        "| ------- | ---------: | ---------: | -----: | -------------------- | ---------: | ----------- | ------- |",
    ]
    for s in sticky_table:
        md_lines.append(
            f"| {s['fixture_id']} {s['fixture_name']} | {s['old_no_bet']} | {s['final_conf']} | "
            f"{s['wde_dq']} | {','.join(s['other_active_reasons']) or '—'} | {s['new_no_bet']} | "
            f"{s['shadow_tier']} | {s['verdict']} |"
        )

    sticky_md = ROOT / "reports" / "research" / "no_bet_sticky_fixture_analysis.md"
    sticky_md.write_text("\n".join(md_lines[md_lines.index("## Sticky cohort (8)") :]) + "\n", encoding="utf-8")
    # Prepend header for sticky-only file
    sticky_md.write_text(
        "# Sticky Fixture Analysis (8)\n\n"
        + "\n".join(md_lines[md_lines.index("## Sticky cohort (8)") :])
        + "\n",
        encoding="utf-8",
    )

    conf_md = [
        "# Confidence Cohort Analysis (15)",
        "",
        "Final confidence was **not** simulated upward. Threshold remains **60**.",
        "",
        "| Fixture | Conf | Still blocked | Reasons | Refresh candidate |",
        "| ------- | ---: | ------------: | ------- | ----------------- |",
    ]
    for c in conf_cohort:
        conf_md.append(
            f"| {c['fixture_id']} | {c['confidence']} | {c['still_blocked']} | "
            f"{','.join(c['active_reasons'])} | {c['refresh_candidate']} |"
        )
    conf_md += [
        "",
        "## Refresh candidates (6)",
        "",
        "May clear only after a **new** fresh-odds ephemeral prediction produces "
        "final confidence ≥60 and zero other active reasons:",
        "",
    ]
    for fid in sorted(REFRESH_CANDIDATES):
        conf_md.append(f"- `{fid}`")
    (ROOT / "reports" / "research" / "no_bet_confidence_cohort_analysis.md").write_text(
        "\n".join(conf_md) + "\n", encoding="utf-8"
    )

    (ROOT / "reports" / "research" / "no_bet_shadow_replay.md").write_text(
        "\n".join(md_lines) + "\n", encoding="utf-8"
    )

    print(json.dumps({"status": status, "categories": categories, "run_id": run_id}, indent=2))
    return 0 if not unexpected else 2


if __name__ == "__main__":
    raise SystemExit(main())
