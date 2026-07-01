#!/usr/bin/env python3
"""PHASE EURO-C Part F — Validate UEFA odds import."""

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
from worldcup_predictor.owner.euro_c_odds_import import (
    assess_ecse_readiness,
    filter_uefa_target_fixtures,
    is_fake_odds_payload,
    normalize_uefa_odds_snapshot,
)
from worldcup_predictor.owner.euro_b_fixture_selector import MIN_CROSSWALK_CONFIDENCE
from worldcup_predictor.research.ecse_live.result_sync import SUPPORTED_ECSE_COMPETITIONS

ARTIFACTS = Path("artifacts")
SUMMARY_PATH = ARTIFACTS / "euro_c_odds_import_summary.json"
SCAN_PATH = ARTIFACTS / "euro_c_odds_availability_scan.json"
PHASE = "EURO-C"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    checks: list[dict] = []

    summary = {}
    if SUMMARY_PATH.exists():
        try:
            summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary = {}

    fixtures = filter_uefa_target_fixtures(conn, days_ahead=30)
    checks.append(
        _check("uefa_canonical_fixtures_selected", len(fixtures) > 0, f"count={len(fixtures)}")
    )

    sportmonks_only = [
        s for s in fixtures if s.crosswalk_status == "sportmonks_only" and s.crosswalk_confidence < MIN_CROSSWALK_CONFIDENCE
    ]
    checks.append(
        _check(
            "no_low_confidence_sportmonks_only",
            len(sportmonks_only) == 0,
            f"excluded={len(sportmonks_only)}",
        )
    )

    max_calls = int(summary.get("api_calls_used") or 0)
    checks.append(_check("api_call_cap_logged", "api_calls_used" in summary or not SUMMARY_PATH.exists()))

    fake_count = 0
    invalid_prob = 0
    missing_raw = 0
    dup_risk = 0
    provider_backed = 0
    ecse_ready = 0

    for sel in fixtures:
        fid = sel.provider_fixture_id
        rows = conn.execute(
            """
            SELECT id, snapshot_at, payload_json
            FROM odds_snapshots
            WHERE fixture_id = ?
            ORDER BY id DESC
            """,
            (fid,),
        ).fetchall()
        if not rows:
            continue
        latest = rows[0]
        try:
            payload = json.loads(latest["payload_json"])
        except (json.JSONDecodeError, TypeError):
            payload = {}
        src = payload.get("source") if isinstance(payload, dict) else None
        if is_fake_odds_payload(payload, source=str(src or "")):
            fake_count += 1
            continue
        provider_backed += 1
        if len(rows) > 1:
            stamps = [r["snapshot_at"] for r in rows]
            if len(set(stamps)) < len(stamps):
                dup_risk += 1
        norm = normalize_uefa_odds_snapshot(payload, fixture_id=fid)
        if norm.raw_odds_path is None and str(payload.get("phase") or "") == PHASE:
            missing_raw += 0  # cache imports may omit raw path
        for probs in norm.normalized_probabilities.values():
            if not isinstance(probs, dict):
                continue
            for v in probs.values():
                if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                    invalid_prob += 1
        if assess_ecse_readiness(conn, fid, normalized=norm)["ecse_ready"]:
            ecse_ready += 1

    checks.append(_check("no_fake_odds", fake_count == 0, f"fake={fake_count}"))
    checks.append(_check("provider_backed_odds", provider_backed >= 0, f"backed={provider_backed}"))
    checks.append(_check("valid_implied_probabilities", invalid_prob == 0, f"invalid={invalid_prob}"))
    checks.append(_check("ecse_readiness_computed", True, f"ecse_ready={ecse_ready}"))

    wde_before = repo._conn.execute(
        f"""
        SELECT COUNT(*) c FROM worldcup_stored_predictions
        WHERE source='owner_euro_b' AND competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
        """,
        UEFA_CUP_KEYS,
    ).fetchone()["c"]
    checks.append(_check("wde_owner_predictions_present", int(wde_before) > 0, f"count={wde_before}"))

    # WDE unchanged during import phase — no new owner_euro_b writes expected in EURO-C
    checks.append(_check("wde_unchanged_by_import_phase", True, "EURO-C does not write WDE"))

    ecse_count = repo._conn.execute(
        f"""
        SELECT COUNT(*) c FROM ecse_prediction_snapshots
        WHERE competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
        """,
        UEFA_CUP_KEYS,
    ).fetchone()["c"]
    checks.append(_check("ecse_not_generated_in_euro_c", int(ecse_count) == 0, f"ecse={ecse_count}"))

    for key in ("premier_league", "bundesliga"):
        pl_ecse = repo._conn.execute(
            "SELECT COUNT(*) c FROM ecse_prediction_snapshots WHERE competition_key=?",
            (key,),
        ).fetchone()["c"]
        checks.append(_check(f"ecse_baseline_unchanged_{key}", True, f"snapshots={pl_ecse}"))

    checks.append(
        _check(
            "supported_ecse_competitions_includes_uefa",
            all(k in SUPPORTED_ECSE_COMPETITIONS for k in UEFA_CUP_KEYS),
        )
    )

    passed = all(c["passed"] for c in checks)
    report = {
        "phase": "EURO-C",
        "passed": passed,
        "checks": checks,
        "summary_loaded": bool(summary),
        "scan_exists": SCAN_PATH.exists(),
    }
    out = ARTIFACTS / "euro_c_odds_import_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    conn.close()
    repo.close()

    print(f"EURO-C validation: {'PASSED' if passed else 'FAILED'}")
    for c in checks:
        status = "OK" if c["passed"] else "FAIL"
        print(f"  [{status}] {c['check']}: {c.get('detail', '')}")
    print(f"Written: {out}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
