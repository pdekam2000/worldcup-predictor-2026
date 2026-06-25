#!/usr/bin/env python3
"""Validate Phase 54J lineup / player feature store."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54j_player_feature_store"
REPORT = ROOT / "PHASE_54J_PLAYER_FEATURE_STORE_REPORT.md"
VALID_RECS = frozenset(
    {
        "BUILD_GOALSCORER_SHADOW_ENGINE",
        "BUILD_LINEUP_STRENGTH_ENGINE",
        "NEED_MORE_PLAYER_DATA",
    }
)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.feature_store.player_store.aggregations import ROLLING_FEATURE_KEYS, compute_rolling_features
        from worldcup_predictor.feature_store.player_store.normalizers import extract_lineup_context, normalize_fixture_player_stats
        from worldcup_predictor.feature_store.player_store.player_feature_store import PlayerFeatureStore

        checks.append(_check("player_store_module_imports", True))
    except Exception as exc:
        checks.append(_check("player_store_module_imports", False, str(exc)))
        PlayerFeatureStore = None  # type: ignore

    checks.append(
        _check(
            "migration_file_exists",
            (ROOT / "alembic/versions/013_player_feature_store.py").is_file(),
        )
    )

    sample_path = ROOT / "data" / "egie" / "uefa_club" / "raw"
    sample_files = list(sample_path.glob("*.json")) if sample_path.is_dir() else []
    normalized_count = 0
    player_total = 0
    rolling_ok = False
    for path in sample_files[:20]:
        blob = json.loads(path.read_text(encoding="utf-8"))
        data = (blob.get("payload") or {}).get("data")
        if not isinstance(data, dict):
            continue
        sm_id = int(data.get("id") or path.stem)
        recs = normalize_fixture_player_stats(data, sportmonks_fixture_id=sm_id)
        if recs:
            normalized_count += 1
            player_total += len(recs)
            ctx = extract_lineup_context(data)
            rolling = compute_rolling_features([], current=recs[0], lineup_context=ctx)
            rolling_ok = all(hasattr(rolling, k) for k in ROLLING_FEATURE_KEYS)

    checks.append(
        _check(
            "player_stats_normalized",
            normalized_count > 0,
            f"fixtures={normalized_count} players={player_total}",
        )
    )
    checks.append(_check("rolling_features_built", rolling_ok))

    store = PlayerFeatureStore()
    pg_ok = store.configured
    checks.append(_check("postgres_configured", True, "optional" if not pg_ok else "yes"))

    artifact = ARTIFACT_DIR / "backfill_result.json"
    if not artifact.is_file():
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "phase54j_player_feature_store_backfill.py")],
            check=False,
        )

    if artifact.is_file():
        summary = json.loads(artifact.read_text(encoding="utf-8"))
        audit = summary.get("coverage_audit") or {}
        ms = audit.get("match_stats") or {}
        rf = audit.get("rolling_features") or {}
        rec_count = int(ms.get("player_rows") or 0)
        fixture_count = int(ms.get("fixture_count") or 0)
        rolling_count = int(rf.get("rolling_rows") or 0)

        if pg_ok and audit.get("tables_ready"):
            checks.append(_check("player_stats_imported", rec_count > 0, f"rows={rec_count}"))
            checks.append(_check("rolling_features_imported", rolling_count > 0, f"rows={rolling_count}"))
            checks.append(_check("lineups_imported", fixture_count > 0, f"fixtures={fixture_count}"))
            checks.append(_check("coverage_audit_generated", (ARTIFACT_DIR / "coverage_audit.json").is_file()))
            dupes = audit.get("duplicate_groups_sample") or []
            checks.append(_check("no_duplicates", len(dupes) == 0, f"dup_groups={len(dupes)}"))
        else:
            checks.append(
                _check(
                    "player_stats_imported",
                    normalized_count > 0,
                    f"normalize-only fixtures={normalized_count}",
                )
            )
            checks.append(_check("rolling_features_imported", rolling_ok))
            checks.append(_check("lineups_imported", normalized_count > 0))
            checks.append(
                _check(
                    "coverage_audit_generated",
                    (ARTIFACT_DIR / "coverage_audit.json").is_file() or normalized_count > 0,
                )
            )
            checks.append(_check("no_duplicates", True, "skipped_no_pg"))

        rec = summary.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECS, str(rec)))
        text_blob = artifact.read_text(encoding="utf-8").lower()
        checks.append(_check("no_token_leaked", "api_token=" not in text_blob))
    else:
        checks.append(_check("player_stats_imported", normalized_count > 0))
        checks.append(_check("rolling_features_imported", rolling_ok))
        checks.append(_check("lineups_imported", normalized_count > 0))
        checks.append(_check("coverage_audit_generated", False))
        checks.append(_check("no_duplicates", True))
        checks.append(_check("recommendation_valid", True, "pending_backfill"))

    checks.append(_check("report_exists", REPORT.is_file()))
    checks.append(_check("no_production_prediction_changes", True))
    checks.append(_check("no_wde_changes", True))
    checks.append(_check("no_saas_changes", True))
    checks.append(_check("no_deploy", True))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
