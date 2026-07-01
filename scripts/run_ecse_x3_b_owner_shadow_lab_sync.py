#!/usr/bin/env python3
"""PHASE ECSE-X3-B — Sync owner shadow lab from M6 rows and write summary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x3_b.constants import SHADOW_ARTIFACT, SUMMARY_ARTIFACT
from worldcup_predictor.research.ecse_x3_b.owner_summary import write_summary
from worldcup_predictor.research.ecse_x3_b.sync import sync_from_m6_shadow

REPORT_PATH = ROOT / "ECSE_X3_B_OWNER_SHADOW_LAB_WIRING_REPORT.md"


def _report_md(payload: dict, sync: dict, baseline_before: int) -> str:
    x3 = payload.get("x3_b") or payload
    cand = x3.get("candidate") or {}
    cmp_b = (x3.get("comparison_vs_baseline") or {})
    cmp_m5 = (x3.get("comparison_vs_m5") or {})
    safety = x3.get("safety") or {}
    reg = x3.get("registry") or {}

    lines = [
        "# ECSE-X3-B — Owner Shadow Lab Wiring Report",
        "",
        "**Phase:** ECSE-X3-B  ",
        "**Mode:** Owner-only shadow wiring — no public prediction changes  ",
        f"**Recommendation:** **{cand.get('recommendation', 'USE_ONLY_HI_J2_G_SLOPE')}**  ",
        f"**Promotion:** {cand.get('promotion_status', 'not_promoted')}  ",
        "",
        "## Candidate registration",
        "",
        f"- **ID:** `{cand.get('id', 'ecse_x3_j2_g_slope')}`",
        f"- **Label:** {cand.get('display_label', 'ECSE X3 — J2/G/OU Slope')}",
        f"- **Mode:** shadow_only",
        f"- **Status:** research_candidate",
        "",
        "## Files",
        "",
        "### Created",
        "- `worldcup_predictor/research/ecse_x3_b/constants.py`",
        "- `worldcup_predictor/research/ecse_x3_b/registry.py`",
        "- `worldcup_predictor/research/ecse_x3_b/runtime.py`",
        "- `worldcup_predictor/research/ecse_x3_b/store.py`",
        "- `worldcup_predictor/research/ecse_x3_b/hook.py`",
        "- `worldcup_predictor/research/ecse_x3_b/sync.py`",
        "- `worldcup_predictor/research/ecse_x3_b/owner_summary.py`",
        "- `scripts/run_ecse_x3_b_owner_shadow_lab_sync.py`",
        "- `scripts/validate_ecse_x3_b_owner_shadow_lab_wiring.py`",
        "",
        "### Modified",
        "- `worldcup_predictor/config/settings.py` — `ECSE_X3_B_OWNER_SHADOW_LAB_ENABLED`",
        "- `worldcup_predictor/research/ecse_x2_m6/hook.py` — X3-B attach after M5",
        "- `worldcup_predictor/research/ecse_x2_m8/lab_service.py` — merge X3 into owner lab",
        "- `worldcup_predictor/research/ecse_x3/mapping.py` — `apply_j2_g_slope_shadow()`",
        "- `base44-d/src/pages/owner/OwnerEcseShadowLab.jsx` — X3 panel",
        "",
        "## Owner-only access",
        "",
        "- **UI:** `/owner/ecse-shadow-lab`",
        "- **API:** `/api/owner/ecse-shadow-lab/summary`, `/fixtures`, `/fixtures/{id}`",
        "- **Auth:** `require_owner_user`",
        "",
        "## Artifacts",
        "",
        f"- `{SHADOW_ARTIFACT}`",
        f"- `{SUMMARY_ARTIFACT}`",
        "",
        "## Sync run",
        "",
        f"- M6 rows processed: **{sync.get('m6_rows_processed', 0)}**",
        f"- X3-B rows written: **{sync.get('rows_written', 0)}**",
        f"- Skipped (duplicate): **{sync.get('rows_skipped', 0)}**",
        "",
        "## Coverage stats",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Evaluated fixtures | {x3.get('evaluated_fixture_count', 0)} |",
        f"| X3 available | {x3.get('x3_available_count', 0)} |",
        f"| X3 unavailable | {x3.get('x3_unavailable_count', 0)} |",
        f"| X3 rejected | {x3.get('x3_rejected_count', 0)} |",
        f"| Coverage % | {x3.get('coverage_percentage', 0)} |",
        "",
        "## Comparison vs baseline",
        "",
        f"- Baseline hit rates: {cmp_b.get('baseline_hit_rates_pct')}",
        f"- X3 hit rates (available only): {cmp_b.get('x3_hit_rates_pct')}",
        f"- Top-1 delta (live slice): {cmp_b.get('x3_delta_top1_pp')} pp",
        "",
        "## Comparison vs M5",
        "",
        f"- M5 applied with actual: {cmp_m5.get('m5_applied_with_actual', 0)}",
        f"- M5 hit rates: {cmp_m5.get('m5_hit_rates_pct')}",
        "",
        "## Missing odds limitations",
        "",
    ]
    for field, count in list((x3.get("missing_field_breakdown") or {}).items())[:8]:
        lines.append(f"- `{field}`: {count}")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            f"- Public predictions unchanged: **{safety.get('public_predictions_unchanged')}**",
            f"- Subscriptions unchanged: **{safety.get('subscriptions_unchanged')}**",
            f"- Baseline table unchanged: **{baseline_before:,}** rows",
            f"- public_prediction_changed rows: **{safety.get('public_prediction_changed_rows', 0)}**",
            f"- Phi forbidden: **{safety.get('phi_forbidden')}**",
            f"- Composite promotion blocked: {reg.get('composite_promotion_blocked')}",
            "",
            "## Validation",
            "",
            "Run:",
            "```bash",
            "python scripts/validate_ecse_x3_b_owner_shadow_lab_wiring.py",
            "python scripts/validate_ecse_x3_a_composite_shadow_engine.py",
            "```",
            "",
            "## Next phase",
            "",
            "**PHASE ECSE-X3-C — Shadow Lab Monitoring and Promotion Threshold Tracking**",
            "(only after X3-B safely wired owner-only)",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        before = baseline_table_row_count(conn)
        sync_result = sync_from_m6_shadow(conn)
        summary_path = write_summary(conn)
        from worldcup_predictor.research.ecse_x2_m8.lab_service import EcseOwnerShadowLabService

        lab_summary = EcseOwnerShadowLabService().summary(conn)
        after = baseline_table_row_count(conn)
    finally:
        conn.close()

    if before != after:
        print("ERROR: baseline table modified", file=sys.stderr)
        return 2

    REPORT_PATH.write_text(_report_md(lab_summary, sync_result, before), encoding="utf-8")
    print(json.dumps(sync_result, indent=2))
    print(f"\nWrote {ROOT / SHADOW_ARTIFACT}")
    print(f"Wrote {summary_path}")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
