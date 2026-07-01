"""Part E/F — Validation and final report for manual owner exact scores."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.owner_manual_exact.constants import (
    ARTIFACTS_DIR,
    FINAL_REPORT,
    PHASE,
    with_safety_labels,
)
from worldcup_predictor.owner_manual_exact.manual_matches import MANUAL_MATCH_LIST
from worldcup_predictor.owner_manual_exact.predictor import _fmt_ou
from worldcup_predictor.owner_manual_exact.resolver import _date_tag
from worldcup_predictor.owner_manual_exact.team_aliases import teams_match
from worldcup_predictor.owner_predict_eval.db_helpers import table_exists
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count


def _table_count(conn, name: str) -> int:
    return table_count(conn, name) if table_exists(conn, name) else 0


def _load_ecse_audit_artifact(process_date: date) -> dict[str, Any] | None:
    path = ARTIFACTS_DIR / f"owner_knockout_ecse_data_audit_{_date_tag(process_date)}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_provider_map_artifact(process_date: date) -> dict[str, Any] | None:
    path = ARTIFACTS_DIR / f"owner_knockout_provider_fixture_map_{_date_tag(process_date)}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_generation_artifact(process_date: date) -> dict[str, Any] | None:
    path = ARTIFACTS_DIR / f"owner_knockout_production_snapshot_generation_{_date_tag(process_date)}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def validate_manual_predictions(
    payload: dict[str, Any],
    *,
    production_before: dict[str, int] | None = None,
    resolution: dict[str, Any] | None = None,
    process_date: date | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    preds = payload.get("predictions") or []

    def chk(name: str, ok: bool, detail: str = "", *, severity: str = "error") -> None:
        entry = {"check": name, "passed": ok, "detail": detail, "severity": severity}
        if severity == "warning" and not ok:
            warnings.append(entry)
            checks.append({**entry, "passed": True})
        else:
            checks.append(entry)

    chk("all_12_matches", len(preds) == 12, f"count={len(preds)}")
    expected_nos = {m["match_no"] for m in MANUAL_MATCH_LIST}
    got_nos = {p.get("match_no") for p in preds}
    chk("match_numbers_complete", expected_nos == got_nos)

    resolved = int(payload.get("resolved_count") or 0)
    chk(
        "fixture_resolution_not_zero_when_imported",
        resolved > 0 or not _provider_had_fixtures(resolution),
        f"resolved={resolved}",
    )
    chk("all_12_resolved", resolved == 12, f"resolved={resolved}")

    fixture_ids = [p.get("fixture_id") for p in preds if p.get("fixture_id")]
    chk("all_resolved_have_fixture_id", len(fixture_ids) == 12, f"fixture_ids={len(fixture_ids)}")
    chk("no_duplicate_fixture_rows", len(fixture_ids) == len(set(fixture_ids)))

    odds_ok = all(p.get("odds_1x2") and p.get("btts_odds") for p in preds)
    chk("screenshot_odds_preserved", odds_ok)

    top_ok = all(p.get("exact_top1") and len(p.get("exact_top3") or []) >= 3 for p in preds)
    chk("exact_top1_and_top3", top_ok)

    audit_ok = all(p.get("source_audit") for p in preds)
    chk("source_audit_present", audit_ok)

    audit_labels = all(
        "production_pick" in (p.get("source_audit") or {})
        and "manual_fallback" in (p.get("source_audit") or {})
        and "production_source" in (p.get("source_audit") or {})
        for p in preds
    )
    chk("pick_origin_labels_present", audit_labels)

    prod_or_fallback = all(
        (p.get("source_audit") or {}).get("production_pick")
        or (p.get("source_audit") or {}).get("manual_fallback")
        for p in preds
    )
    chk("every_match_production_or_fallback", prod_or_fallback)

    shadow_not_prod = all(
        (p.get("source_audit") or {}).get("production_source") != "wde_shadow"
        and (p.get("source_audit") or {}).get("WDE_shadow_label") != "PRODUCTION"
        for p in preds
    )
    chk("shadow_not_promoted_as_production", shadow_not_prod)

    for p in preds:
        audit = p.get("source_audit") or {}
        if audit.get("fallback_used") and not audit.get("ecse_attached") and not audit.get("wde_attached"):
            chk(
                f"missing_attachment_{p.get('fixture_id')}",
                False,
                audit.get("missing_reason") or "no_production_attachment",
                severity="warning",
            )

    # alias smoke tests
    chk("alias_dr_kongo", teams_match("DR Kongo", "Congo DR"))
    chk("alias_bosnia_de", teams_match("Bosnien-Herzegowina", "Bosnia & Herzegovina"))
    chk("alias_egypt_de", teams_match("Ägypten", "Egypt"))

    json_path = payload.get("json_path", "")
    md_path = payload.get("md_path", "")
    chk("json_artifact_exists", Path(json_path).exists() if json_path else False, json_path)
    chk("md_report_exists", Path(md_path).exists() if md_path else False, md_path)

    gen_artifact = _load_generation_artifact(process_date) if process_date else None
    ecse_audit = _load_ecse_audit_artifact(process_date) if process_date else None
    provider_map = _load_provider_map_artifact(process_date) if process_date else None

    if ecse_audit:
        audit_by_fid = {
            int(f["local_fixture_id"]): f for f in (ecse_audit.get("fixtures") or []) if f.get("local_fixture_id")
        }
        for p in preds:
            fid = p.get("fixture_id")
            if not fid:
                continue
            fx_audit = audit_by_fid.get(int(fid), {})
            audit = p.get("source_audit") or {}
            min_met = bool(fx_audit.get("minimum_ecse_inputs_met"))
            has_ecse = bool(audit.get("ecse_attached"))
            if min_met and not has_ecse:
                chk(
                    f"ecse_missing_despite_minimum_data_{fid}",
                    False,
                    fx_audit.get("ecse_reason") or "minimum_inputs_met_but_no_ecse",
                )
            elif not has_ecse and fx_audit.get("ecse_reason", "").startswith("ecse_not_generated"):
                chk(
                    f"ecse_skipped_without_generation_{fid}",
                    False,
                    fx_audit.get("ecse_reason"),
                )
            elif has_ecse and not (fx_audit.get("xg_available") or fx_audit.get("pressure_available")):
                chk(
                    f"partial_ecse_without_xg_pressure_{fid}",
                    False,
                    f"layers={audit.get('ecse_layers_used')} completeness={audit.get('ecse_completeness_score')}",
                    severity="warning",
                )

    if provider_map:
        for mapping in provider_map.get("mappings") or []:
            local_id = mapping.get("local_fixture_id")
            if not local_id:
                continue
            if not mapping.get("sportmonks_fixture_id") and mapping.get("api_football_fixture_id"):
                chk(
                    f"sportmonks_mapping_missing_{local_id}",
                    False,
                    f"api_football={mapping.get('api_football_fixture_id')} crosswalk={mapping.get('crosswalk_method')}",
                    severity="warning",
                )

    if gen_artifact:
        for row in gen_artifact.get("per_fixture") or []:
            ecse = row.get("ecse") or {}
            if ecse.get("status") == "skipped" and not ecse.get("reason"):
                chk(f"ecse_skip_no_reason_{row.get('fixture_id')}", False, "missing skip reason in generation artifact")

    if gen_artifact:
        chk("generation_owner_only", gen_artifact.get("OWNER_ONLY") is True)
        chk("generation_public_publish_false", gen_artifact.get("PUBLIC_PUBLISH") is False)
        chk("generation_no_wde_retrain", gen_artifact.get("WDE_RETRAINED") is False)
    elif production_before:
        conn = connect_readonly(get_db_path())
        after_wde = _table_count(conn, "worldcup_stored_predictions")
        after_odds = _table_count(conn, "odds_snapshots")
        after_ecse = _table_count(conn, "ecse_prediction_snapshots")
        conn.close()
        chk("no_wde_production_writes", after_wde == production_before.get("worldcup_stored_predictions", after_wde))
        chk("no_odds_snapshots_writes", after_odds == production_before.get("odds_snapshots", after_odds))
        chk("no_ecse_snapshot_writes", after_ecse == production_before.get("ecse_prediction_snapshots", after_ecse))

    chk("public_publish_false", payload.get("PUBLIC_PUBLISH") is False)

    recommendation = derive_recommendation(payload, checks, resolution=resolution, warnings=warnings)
    return {
        "phase": PHASE,
        "passed": sum(1 for c in checks if c["passed"] and c.get("severity", "error") == "error"),
        "failed": sum(1 for c in checks if not c["passed"] and c.get("severity", "error") == "error"),
        "warnings": len(warnings),
        "checks": checks,
        "warning_details": warnings,
        "final_recommendation": recommendation,
        "generation_artifact_loaded": gen_artifact is not None,
        "ecse_audit_loaded": ecse_audit is not None,
        "provider_map_loaded": provider_map is not None,
    }


def _provider_had_fixtures(resolution: dict[str, Any] | None) -> bool:
    if not resolution:
        return False
    imp = resolution.get("import_audit") or {}
    return int(imp.get("api_fetched") or 0) >= 12


def derive_recommendation(
    payload: dict[str, Any],
    checks: list[dict[str, Any]],
    *,
    resolution: dict[str, Any] | None = None,
    warnings: list[dict[str, Any]] | None = None,
) -> str:
    if any(c["check"] == "fixture_resolution_not_zero_when_imported" and not c["passed"] for c in checks):
        return "NEED_FIXTURE_RESOLUTION"
    if any(c["check"] == "all_12_resolved" and not c["passed"] for c in checks):
        return "NEED_FIXTURE_RESOLUTION"
    if any(c["check"] == "all_12_matches" and not c["passed"] for c in checks):
        return "NEED_FIXTURE_RESOLUTION"
    if any(c["check"] == "shadow_not_promoted_as_production" and not c["passed"] for c in checks):
        return "SHADOW_PROMOTION_BLOCKED"
    if any(c["check"] == "public_publish_false" and not c["passed"] for c in checks):
        return "PUBLIC_PUBLISH_BLOCKED"

    preds = payload.get("predictions") or []
    resolved = int(payload.get("resolved_count") or 0)
    wde_used = sum(1 for p in preds if (p.get("source_audit") or {}).get("wde_attached"))
    ecse_used = sum(1 for p in preds if (p.get("source_audit") or {}).get("ecse_attached"))
    fallback_count = sum(1 for p in preds if (p.get("source_audit") or {}).get("fallback_used"))

    if any(not c["passed"] for c in checks if c.get("severity", "error") == "error" and c["check"] in ("exact_top1_and_top3", "source_audit_present", "every_match_production_or_fallback")):
        return "NEED_MODEL_OUTPUTS"

    if resolved == 12 and (wde_used > 0 or ecse_used > 0) and fallback_count < 12:
        return "OWNER_DAILY_READY_WITH_PRODUCTION_ATTACHMENTS"
    if resolved == 12 and (wde_used > 0 or ecse_used > 0):
        return "OWNER_DAILY_READY_WITH_PARTIAL_PRODUCTION_ATTACHMENTS"
    if 0 < resolved < 12:
        return "READY_PARTIAL_FIXTURE_RESOLUTION"
    if resolved == 0:
        return "READY_WITH_MANUAL_ODDS_ONLY"
    if resolved == 12 and wde_used == 0 and ecse_used == 0:
        return "READY_PARTIAL_FIXTURE_RESOLUTION"
    return "MANUAL_EXACT_SCORE_REPORT_READY"


def write_final_report(
    payload: dict[str, Any],
    validation: dict[str, Any],
    *,
    process_date: date,
    resolution: dict[str, Any] | None = None,
) -> None:
    preds = payload.get("predictions") or []
    by_conf = sorted(preds, key=lambda p: float(p.get("confidence") or 0), reverse=True)
    strongest = by_conf[:3]
    weakest = sorted(preds, key=lambda p: float(p.get("confidence") or 0))[:3]
    imp = (resolution or {}).get("import_audit") or {}

    unresolved = [
        f"{r.get('home_team_input')} vs {r.get('away_team_input')}: {r.get('resolution', {}).get('reject_reasons', r.get('resolution', {}).get('note'))}"
        for r in (resolution or {}).get("matches") or []
        if (r.get("resolution") or {}).get("resolution_status") != "RESOLVED"
    ]

    md_table_lines = []
    for p in preds:
        top3 = ", ".join(p.get("exact_top3") or [])
        audit = p.get("source_audit") or {}
        origin = audit.get("production_source") or ("manual-fallback" if audit.get("manual_fallback") else "production")
        md_table_lines.append(
            f"| {p.get('home_team')} vs {p.get('away_team')} | {p.get('fixture_id')} | {p.get('kickoff_label')} | "
            f"{audit.get('production_source', '—')} | {audit.get('exact_score_source', '—')} | "
            f"{'yes' if audit.get('ecse_attached') else 'no'} | {'yes' if audit.get('wde_attached') else 'no'} | "
            f"{'yes' if audit.get('fallback_used') else 'no'} | "
            f"{p.get('pick_1x2_display')} | {p.get('exact_top1')} | {top3} | "
            f"{p.get('pick_btts')} | {_fmt_ou(p.get('pick_ou25'))} | "
            f"{p.get('confidence')} | {p.get('risk_badge')} | {p.get('best_tip')} | {p.get('source_summary')} ({origin}) |"
        )

    shadow_note = payload.get("wde_shadow_global_status") or {}
    md = f"""# Manual Owner Exact Score Prediction Report

**Phase:** {PHASE}  
**Process date:** {process_date.isoformat()}  
**Mode:** Owner/internal only — no public publish

## Summary

- Resolved fixtures: **{payload.get('resolved_count', 0)}** / 12
- Fixtures inserted: **{imp.get('inserted', 0)}** | updated: **{imp.get('updated', 0)}** | skipped duplicates: **{imp.get('skipped_duplicate', 0)}**
- Manual-only (no internal fixture): **{payload.get('manual_only_count', 0)}**
- WDE production used: **{(payload.get('engines') or {}).get('wde_production', 0)}**
- ECSE production used: **{(payload.get('engines') or {}).get('ecse_production', 0)}**
- WDE shadow (SHADOW_ONLY): **{(payload.get('engines') or {}).get('wde_shadow', 0)}**
- OddAlerts shadow: **{(payload.get('engines') or {}).get('oddalerts_shadow', 0)}**

WDE shadow status: `{shadow_note.get('label', 'n/a')}` — recommendation `{shadow_note.get('recommendation', 'n/a')}` (not promoted).

## Unresolved matches

{chr(10).join(f"- {u}" for u in unresolved) if unresolved else "- None — all 12 resolved"}

## Strongest 3 predictions (by confidence)

{chr(10).join(f"- **{p.get('home_team')} vs {p.get('away_team')}** — Endergebnis `{p.get('exact_top1')}`, conf {p.get('confidence')}" for p in strongest)}

## Highest-risk 3 predictions

{chr(10).join(f"- **{p.get('home_team')} vs {p.get('away_team')}** — risk `{p.get('risk_badge')}`, source `{p.get('source_summary')}`" for p in weakest)}

## Endergebnis / نتیجه دقیق نهایی

| Match | fixture_id | Time | Production | Exact source | ECSE | WDE | Fallback | 1X2 | Top-1 | Top-3 | BTTS | O/U | Conf | Risk | Tip | Source |
| ----- | ---------- | ---- | ---------- | ------------ | ---- | --- | -------- | --- | ----- | ----- | ---- | --- | ---- | ---- | --- | ------ |
{chr(10).join(md_table_lines)}

## Validation

- Checks passed: **{validation.get('passed')}** / {validation.get('passed', 0) + validation.get('failed', 0)}
- Warnings: **{validation.get('warnings', 0)}**
- Final recommendation: **`{validation.get('final_recommendation')}`**

## Disclaimer

These are model/odds-based predictions, not guaranteed results. **Production pick** = ECSE (preferred) or WDE attached via `fixture_id`. **Manual fallback** = screenshot odds Poisson when production exact score unavailable. WDE shadow = **SHADOW_ONLY** comparison — never promoted.

**No public publish.** Production writes occur only via owner-only knockout generation (`owner_knockout_production`).
"""
    FINAL_REPORT.write_text(md, encoding="utf-8")
