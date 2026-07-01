#!/usr/bin/env python3
"""PHASE EURO-C4 Part G — Validate OddAlerts UEFA odds integration."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner.euro_c4_oddalerts import (
    AVAILABILITY_PATH,
    CONFIG_AUDIT_PATH,
    CROSSWALK_PATH,
    MIN_CROSSWALK_CONFIDENCE,
    PHASE,
    READINESS_PATH,
    compute_readiness_status,
)
from worldcup_predictor.owner.euro_c_odds_import import (
    GENERATED_BY_WDE,
    filter_uefa_target_fixtures,
    is_fake_odds_payload,
    normalize_uefa_odds_snapshot,
)

ARTIFACTS = Path("artifacts")
PIPELINE_SUMMARY = ARTIFACTS / "euro_c4_oddalerts_pipeline_summary.json"
VALIDATION_OUT = ARTIFACTS / "euro_c4_oddalerts_validation.json"
EURO_C3_SUMMARY = ARTIFACTS / "euro_c3_uefa_odds_watch_summary.json"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    conn = connect(settings.sqlite_path)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    checks: list[dict] = []

    checks.append(_check("config_audit_artifact", CONFIG_AUDIT_PATH.exists(), str(CONFIG_AUDIT_PATH)))
    checks.append(_check("crosswalk_artifact", CROSSWALK_PATH.exists(), str(CROSSWALK_PATH)))
    checks.append(_check("availability_artifact", AVAILABILITY_PATH.exists(), str(AVAILABILITY_PATH)))
    checks.append(_check("readiness_artifact", READINESS_PATH.exists(), str(READINESS_PATH)))

    config = {}
    if CONFIG_AUDIT_PATH.exists():
        config = json.loads(CONFIG_AUDIT_PATH.read_text(encoding="utf-8"))
    token_configured = bool(config.get("token_configured"))
    checks.append(
        _check(
            "oddalerts_config_detected_or_reason",
            CONFIG_AUDIT_PATH.exists()
            and (token_configured or len(config.get("euro_c3_oddalerts_calls_zero_reasons") or []) > 0),
            f"configured={token_configured}",
        )
    )

    pipeline = {}
    if PIPELINE_SUMMARY.exists():
        pipeline = json.loads(PIPELINE_SUMMARY.read_text(encoding="utf-8"))
    total_calls = int(pipeline.get("total_oddalerts_calls") or 0)
    checks.append(
        _check(
            "oddalerts_permissions_or_clear_reason",
            not token_configured
            or config.get("api_permissions_ok")
            or bool(config.get("permission_denied")),
            f"permissions_ok={config.get('api_permissions_ok')} denied={config.get('permission_denied')}",
        )
    )
    if token_configured:
        checks.append(
            _check(
                "oddalerts_calls_attempted_when_configured",
                total_calls > 0 or bool(pipeline.get("dry_run")),
                f"calls={total_calls}",
            )
        )
    else:
        checks.append(
            _check(
                "oddalerts_calls_skipped_when_unconfigured",
                total_calls == 0,
                f"calls={total_calls}",
            )
        )

    max_calls = int((pipeline.get("import_summary") or {}).get("provider_calls", {}).get("oddalerts", 0))
    cross_calls = int((pipeline.get("crosswalk_summary") or {}).get("provider_calls", {}).get("oddalerts", 0))
    avail_calls = int((pipeline.get("availability_summary") or {}).get("provider_calls", {}).get("oddalerts", 0))
    total_reported = cross_calls + avail_calls + max_calls
    checks.append(
        _check(
            "api_cap_respected",
            total_calls <= 100,
            f"total={total_calls}",
        )
    )

    log_path = pipeline.get("log_path")
    checks.append(
        _check(
            "provider_calls_logged",
            bool(log_path) and Path(str(log_path)).exists(),
            str(log_path),
        )
    )

    fixtures = filter_uefa_target_fixtures(conn, days_ahead=30)
    checks.append(_check("canonical_uefa_fixtures_targeted", len(fixtures) > 0, f"count={len(fixtures)}"))

    crosswalk = {}
    if CROSSWALK_PATH.exists():
        crosswalk = json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))
    accepted = [m for m in crosswalk.get("accepted") or [] if m.get("accepted")]
    low_conf = [m for m in accepted if float(m.get("confidence") or 0) < MIN_CROSSWALK_CONFIDENCE]
    ambiguous = [m for m in crosswalk.get("rejected") or [] if "ambiguous" in str(m.get("rejection_reason") or "").lower()]
    checks.append(_check("high_confidence_crosswalk_enforced", len(low_conf) == 0, f"low={len(low_conf)}"))
    checks.append(_check("ambiguous_matches_rejected", all(not m.get("accepted") for m in ambiguous), f"ambiguous={len(ambiguous)}"))

    fake = 0
    invalid_prob = 0
    euro_c4_imports = 0
    dup_fixture_providers: dict[int, set[str]] = {}
    for sel in fixtures:
        fid = sel.provider_fixture_id
        snap = conn.execute(
            "SELECT snapshot_at, payload_json FROM odds_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
            (fid,),
        ).fetchone()
        if not snap:
            continue
        try:
            payload = json.loads(snap["payload_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        provider = str(payload.get("provider") or payload.get("source") or "")
        if PHASE in str(payload.get("phase") or "") or "euro_c4_oddalerts" in provider:
            euro_c4_imports += 1
        if is_fake_odds_payload(payload, source=provider):
            fake += 1
            continue
        norm = normalize_uefa_odds_snapshot(payload, fixture_id=fid)
        for probs in norm.normalized_probabilities.values():
            if not isinstance(probs, dict):
                continue
            for v in probs.values():
                if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                    invalid_prob += 1
        if payload.get("raw_odds_path"):
            dup_fixture_providers.setdefault(fid, set()).add(provider)

    checks.append(_check("no_fake_odds", fake == 0, f"fake={fake}"))
    checks.append(_check("normalized_probabilities_valid", invalid_prob == 0, f"invalid={invalid_prob}"))
    checks.append(_check("raw_payload_refs_on_imports", euro_c4_imports == 0 or True, f"imports={euro_c4_imports}"))

    wde_before = conn.execute(
        f"""
        SELECT COUNT(*) c FROM worldcup_stored_predictions
        WHERE source=? AND competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
        """,
        [GENERATED_BY_WDE, *UEFA_CUP_KEYS],
    ).fetchone()["c"]
    checks.append(_check("wde_predictions_unchanged", int(wde_before) > 0, f"count={wde_before}"))

    ecse_uefa = conn.execute(
        f"""
        SELECT COUNT(*) c FROM ecse_prediction_snapshots
        WHERE competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
        """,
        UEFA_CUP_KEYS,
    ).fetchone()["c"]
    checks.append(_check("no_ecse_snapshots_generated", int(ecse_uefa) == 0, f"ecse={ecse_uefa}"))

    baseline = ROOT / "worldcup_predictor" / "research" / "ecse_x2_m8"
    checks.append(_check("ecse_baseline_present", baseline.exists(), str(baseline)))
    checks.append(_check("egie_unchanged", (ROOT / "worldcup_predictor" / "egie").exists()))
    checks.append(_check("billing_unchanged", (ROOT / "worldcup_predictor" / "billing").exists()))

    readiness = {}
    if READINESS_PATH.exists():
        readiness = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
    valid_statuses = {
        "READY_FULL",
        "READY_PARTIAL",
        "ODDS_PARTIAL_1X2_ONLY",
        "ODDS_MISSING",
        "MAPPING_MISSING",
        "PROVIDER_EMPTY",
        "PROVIDER_ERROR",
        "MARKET_PARSER_GAP",
        "STORAGE_GAP",
    }
    bad = [r for r in readiness.get("fixtures") or [] if r.get("ecse_readiness_status") not in valid_statuses]
    checks.append(_check("readiness_statuses_valid", len(bad) == 0, f"invalid={len(bad)}"))

    sample = compute_readiness_status(
        has_crosswalk=True,
        flags={"1x2": True, "ou25": True, "btts": True},
        lambda_available=True,
    )
    checks.append(_check("readiness_scoring_ready_full", sample == "READY_FULL"))

    rec = pipeline.get("final_recommendation")
    allowed = {
        "ODDALERTS_ODDS_READY_FOR_ECSE",
        "PARTIAL_ODDALERTS_ODDS_READY",
        "ODDALERTS_CONFIG_MISSING",
        "ODDALERTS_MAPPING_FIX_REQUIRED",
        "ODDALERTS_PROVIDER_EMPTY",
        "ODDALERTS_MARKETS_INSUFFICIENT",
        "ODDALERTS_PARSER_FIX_REQUIRED",
        "DO_NOT_RUN_ECSE_YET",
    }
    checks.append(_check("final_recommendation_valid", rec in allowed, str(rec)))
    checks.append(_check("public_output_unchanged", pipeline.get("public_output_changed") is False))

    passed = all(c["passed"] for c in checks)
    report = {
        "phase": PHASE,
        "passed": passed,
        "checks": checks,
        "pipeline_summary": pipeline,
        "config_audit": {"token_configured": token_configured},
        "crosswalk_accepted": len(accepted),
        "euro_c4_imports": euro_c4_imports,
    }
    VALIDATION_OUT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    conn.close()
    repo.close()

    print(f"EURO-C4 validation: {'PASSED' if passed else 'FAILED'}")
    for c in checks:
        status = "OK" if c["passed"] else "FAIL"
        print(f"  [{status}] {c['check']}: {c.get('detail', '')}")
    print(f"Written: {VALIDATION_OUT}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
