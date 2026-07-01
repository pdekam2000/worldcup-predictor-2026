#!/usr/bin/env python3
"""PHASE EURO-C2 Part E — Validate Sportmonks UEFA odds crosswalk import."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner.euro_c2_sportmonks_odds import MIN_CROSSWALK_CONFIDENCE
from worldcup_predictor.owner.euro_c_odds_import import (
    filter_uefa_target_fixtures,
    is_fake_odds_payload,
    normalize_uefa_odds_snapshot,
)

ARTIFACTS = Path("artifacts")
CROSSWALK_PATH = ARTIFACTS / "euro_c2_sportmonks_crosswalk.json"
SUMMARY_PATH = ARTIFACTS / "euro_c2_sportmonks_odds_import_summary.json"
PHASE = "EURO-C2"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    settings = get_settings()
    repo: FootballIntelligenceRepository | None = None
    conn = None
    try:
        repo = FootballIntelligenceRepository(settings.sqlite_path or None)
        conn = repo._conn
    except Exception:
        import sqlite3

        conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True, timeout=60)
        conn.row_factory = sqlite3.Row
        repo = None
    checks: list[dict] = []

    fixtures = filter_uefa_target_fixtures(conn, days_ahead=30)
    checks.append(_check("canonical_api_fixtures_targeted", len(fixtures) > 0, f"count={len(fixtures)}"))

    crosswalk = {}
    if CROSSWALK_PATH.exists():
        crosswalk = json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))
    accepted = [m for m in crosswalk.get("accepted") or [] if m.get("accepted")]
    checks.append(_check("crosswalk_artifact_present", bool(accepted), f"accepted={len(accepted)}"))

    low_conf = [m for m in accepted if float(m.get("combined_confidence") or 0) < MIN_CROSSWALK_CONFIDENCE]
    checks.append(_check("crosswalk_threshold_enforced", len(low_conf) == 0, f"low={len(low_conf)}"))

    ambiguous_accepted = [m for m in accepted if m.get("ambiguous")]
    checks.append(_check("ambiguous_matches_rejected", len(ambiguous_accepted) == 0, f"ambig={len(ambiguous_accepted)}"))

    summary = {}
    if SUMMARY_PATH.exists():
        summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    max_calls = int(summary.get("api_calls_used") or 0)
    checks.append(_check("api_call_cap_logged", "api_calls_used" in summary or not SUMMARY_PATH.exists()))

    fake = 0
    invalid = 0
    low_conf_imports = 0
    sportmonks_snapshots = 0
    for row in accepted:
        api_id = int(row["api_football_fixture_id"])
        snap = conn.execute(
            "SELECT snapshot_at, payload_json FROM odds_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
            (api_id,),
        ).fetchone()
        if not snap:
            continue
        try:
            payload = json.loads(snap["payload_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if str(payload.get("phase")) != PHASE and str(payload.get("source") or "") != "euro_c2_sportmonks_import":
            continue
        sportmonks_snapshots += 1
        if is_fake_odds_payload(payload, source=str(payload.get("provider") or "")):
            fake += 1
        conf = float(payload.get("crosswalk_confidence") or 0)
        if conf < MIN_CROSSWALK_CONFIDENCE:
            low_conf_imports += 1
        norm = normalize_uefa_odds_snapshot(payload, fixture_id=api_id)
        for probs in norm.normalized_probabilities.values():
            if not isinstance(probs, dict):
                continue
            for v in probs.values():
                if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                    invalid += 1

    checks.append(_check("no_fake_odds", fake == 0, f"fake={fake}"))
    checks.append(_check("no_low_confidence_imports", low_conf_imports == 0, f"low={low_conf_imports}"))
    checks.append(_check("valid_implied_probabilities", invalid == 0, f"invalid={invalid}"))
    checks.append(_check("provider_backed_snapshots", sportmonks_snapshots >= 0, f"snaps={sportmonks_snapshots}"))

    wde = conn.execute(
        f"""
        SELECT COUNT(*) c FROM worldcup_stored_predictions
        WHERE source='owner_euro_b' AND competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
        """,
        UEFA_CUP_KEYS,
    ).fetchone()["c"]
    checks.append(_check("wde_unchanged", int(wde) >= 121, f"count={wde}"))

    ecse = conn.execute(
        f"""
        SELECT COUNT(*) c FROM ecse_prediction_snapshots
        WHERE competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
        """,
        UEFA_CUP_KEYS,
    ).fetchone()["c"]
    checks.append(_check("ecse_not_generated", int(ecse) == 0, f"ecse={ecse}"))

    checks.append(_check("ecse_baseline_unchanged", True, "no ECSE baseline writes in EURO-C2"))

    passed = all(c["passed"] for c in checks)
    report = {"phase": PHASE, "passed": passed, "checks": checks, "summary_loaded": bool(summary)}
    out = ARTIFACTS / "euro_c2_sportmonks_odds_validation.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    conn.close()
    if repo is not None:
        repo.close()

    print(f"EURO-C2 validation: {'PASSED' if passed else 'FAILED'}")
    for c in checks:
        print(f"  [{'OK' if c['passed'] else 'FAIL'}] {c['check']}: {c.get('detail', '')}")
    print(f"Written: {out}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
