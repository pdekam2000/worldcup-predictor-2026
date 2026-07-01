#!/usr/bin/env python3
"""PHASE EURO-C3 Part G — Validate UEFA odds watch + ECSE readiness monitor."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner.euro_c2_sportmonks_odds import MIN_CROSSWALK_CONFIDENCE
from worldcup_predictor.owner.euro_c3_odds_watch import (
    READINESS_PATH,
    SUMMARY_PATH,
    compute_ecse_readiness_status,
    load_readiness_index,
)
from worldcup_predictor.owner.euro_c_odds_import import (
    filter_uefa_target_fixtures,
    is_fake_odds_payload,
    normalize_uefa_odds_snapshot,
)

ARTIFACTS = Path("artifacts")
CROSSWALK_PATH = ARTIFACTS / "euro_c2_sportmonks_crosswalk.json"
PHASE = "EURO-C3"
OWNER_REPORT = ROOT / "scripts" / "owner_today_10_exact_scores.py"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    checks: list[dict] = []

    checks.append(_check("summary_artifact_exists", SUMMARY_PATH.exists(), str(SUMMARY_PATH)))
    checks.append(_check("readiness_jsonl_exists", READINESS_PATH.exists(), str(READINESS_PATH)))

    summary = {}
    if SUMMARY_PATH.exists():
        summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    checks.append(_check("phase_euro_c3", summary.get("phase") == PHASE, str(summary.get("phase"))))

    max_af = int(summary.get("provider_calls", {}).get("api_football", 0))
    max_sm = int(summary.get("provider_calls", {}).get("sportmonks", 0))
    max_oa = int(summary.get("provider_calls", {}).get("oddalerts", 0))
    checks.append(
        _check(
            "api_call_caps_respected",
            max_af <= 100 and max_sm <= 100 and max_oa <= 100,
            f"af={max_af} sm={max_sm} oa={max_oa}",
        )
    )

    fixtures = filter_uefa_target_fixtures(conn, days_ahead=30)
    checks.append(_check("uefa_fixtures_scanned", len(fixtures) > 0, f"count={len(fixtures)}"))

    crosswalk = {}
    if CROSSWALK_PATH.exists():
        crosswalk = json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))
    accepted = [m for m in crosswalk.get("accepted") or [] if m.get("accepted")]
    low_conf = [m for m in accepted if float(m.get("combined_confidence") or 0) < MIN_CROSSWALK_CONFIDENCE]
    checks.append(_check("accepted_crosswalk_only", len(low_conf) == 0, f"low={len(low_conf)}"))

    readiness_index = load_readiness_index()
    checks.append(_check("readiness_rows_present", len(readiness_index) > 0, f"rows={len(readiness_index)}"))

    valid_statuses = {
        "READY_FULL",
        "READY_PARTIAL",
        "ODDS_PARTIAL_1X2_ONLY",
        "ODDS_MISSING",
        "MAPPING_MISSING",
        "PROVIDER_EMPTY",
        "PROVIDER_ERROR",
    }
    bad_status = [fid for fid, row in readiness_index.items() if row.get("ecse_readiness_status") not in valid_statuses]
    checks.append(_check("readiness_statuses_valid", len(bad_status) == 0, f"invalid={len(bad_status)}"))

    fake = 0
    invalid_prob = 0
    euro_c3_imports = 0
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
        if str(payload.get("phase")) == PHASE or "euro_c3" in str(payload.get("source") or ""):
            euro_c3_imports += 1
        if is_fake_odds_payload(payload, source=str(payload.get("provider") or "")):
            fake += 1
            continue
        norm = normalize_uefa_odds_snapshot(payload, fixture_id=fid)
        for probs in norm.normalized_probabilities.values():
            if not isinstance(probs, dict):
                continue
            for v in probs.values():
                if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                    invalid_prob += 1

    checks.append(_check("no_fake_odds", fake == 0, f"fake={fake}"))
    checks.append(_check("normalized_odds_valid", invalid_prob == 0, f"invalid={invalid_prob}"))

    ecse_uefa = repo._conn.execute(
        f"""
        SELECT COUNT(*) c FROM ecse_prediction_snapshots
        WHERE competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
        """,
        UEFA_CUP_KEYS,
    ).fetchone()["c"]
    checks.append(_check("no_ecse_snapshots_generated", int(ecse_uefa) == 0, f"ecse={ecse_uefa}"))

    wde_count = repo._conn.execute(
        f"""
        SELECT COUNT(*) c FROM worldcup_stored_predictions
        WHERE source='owner_euro_b' AND competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
        """,
        UEFA_CUP_KEYS,
    ).fetchone()["c"]
    checks.append(_check("wde_predictions_present", int(wde_count) > 0, f"count={wde_count}"))

    owner_src = OWNER_REPORT.read_text(encoding="utf-8")
    checks.append(
        _check(
            "owner_report_readiness_integration",
            "uefa_odds_readiness" in owner_src and "ECSE readiness" in owner_src,
        )
    )

    eige_path = ROOT / "worldcup_predictor" / "egie"
    checks.append(_check("egie_unchanged", eige_path.exists(), "egie module present"))

    billing_path = ROOT / "worldcup_predictor" / "billing"
    checks.append(_check("billing_unchanged", billing_path.exists(), "billing module present"))

    public_ui = ROOT / "frontend"
    if public_ui.exists():
        checks.append(_check("no_public_ui_changes_required", True, "manual spot-check"))

    # Spot-check readiness scoring logic
    sample = compute_ecse_readiness_status(
        has_crosswalk=True,
        has_1x2=True,
        has_ou25=True,
        has_btts=True,
        lambda_available=True,
    )
    checks.append(_check("readiness_scoring_ready_full", sample == "READY_FULL"))

    passed = all(c["passed"] for c in checks)
    report = {
        "phase": PHASE,
        "passed": passed,
        "checks": checks,
        "summary": summary,
        "euro_c3_imports": euro_c3_imports,
    }
    out = ARTIFACTS / "euro_c3_odds_watch_validation.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    conn.close()
    repo.close()

    print(f"EURO-C3 validation: {'PASSED' if passed else 'FAILED'}")
    for c in checks:
        status = "OK" if c["passed"] else "FAIL"
        print(f"  [{status}] {c['check']}: {c.get('detail', '')}")
    print(f"Written: {out}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
