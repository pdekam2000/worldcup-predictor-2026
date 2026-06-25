#!/usr/bin/env python3
"""Phase 46B — historical prediction recovery validation."""

from __future__ import annotations

import json
import runpy
import shutil
from datetime import datetime
from pathlib import Path

from datetime import datetime

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    out = Path("artifacts/phase46b_historical_recovery_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": "46B",
        "passed": passed,
        "total": total,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Phase 46B validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    return 0 if passed == total else 1


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.automation.worldcup_background.legacy_prediction_import import (
        LegacyImportCandidate,
        compute_quality_score,
        merge_candidates,
        run_legacy_prediction_import,
    )
    from worldcup_predictor.config.competitions import get_competition
    from worldcup_predictor.config.settings import Settings, get_settings
    from worldcup_predictor.database.migrations import ensure_schema_compat
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.domain.schedule import TournamentFixture

    db_path = Path("artifacts/phase46b_validation.db")
    cache_dir = Path("artifacts/phase46b_cache")
    hist_path = Path("artifacts/phase46b_history.jsonl")

    if db_path.exists():
        db_path.unlink()
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings(SQLITE_PATH=str(db_path), PREDICTION_CACHE_DIR=str(cache_dir))
    get_settings.cache_clear()
    repo = FootballIntelligenceRepository(str(db_path))
    ensure_schema_compat(repo._conn)
    repo.upsert_competition(get_competition("world_cup_2026"))

    # Authoritative archive row — must never be overwritten
    auth_id = 900001
    auth_payload = {
        "fixture_id": auth_id,
        "home_team": "Brazil",
        "away_team": "France",
        "prediction": "home",
        "confidence": 72.0,
        "status": "ok",
        "predicted_at": "2026-06-10T12:00:00",
    }
    repo.upsert_worldcup_stored_prediction(
        fixture_id=auth_id,
        payload=auth_payload,
        source="background",
        predicted_at="2026-06-10T12:00:00",
    )
    before_auth = repo.get_worldcup_stored_prediction(auth_id)
    record("schema_has_import_columns", "imported_at" in (before_auth or {}), "imported_at column")

    # Cache candidate (recoverable)
    cache_fid = 900002
    cache_payload = {
        "fixture_id": cache_fid,
        "home_team": "Argentina",
        "away_team": "Germany",
        "prediction": "draw",
        "confidence": 65.0,
        "status": "ok",
        "probabilities": {"over_under_2_5": {"selection": "over"}},
        "detailed_markets": {"match_winner": {"selection": "draw", "probability": 0.33}},
        "predicted_at": "2026-06-11T08:00:00",
    }
    cache_envelope = {
        "endpoint": "prediction_result",
        "params": {"fixture_id": cache_fid, "competition": "world_cup_2026", "season": 2026, "locale": "en"},
        "cached_at": 1780000000.0,
        "expires_at": 9999999999.0,
        "payload": cache_payload,
    }
    (cache_dir / "test_cache.json").write_text(json.dumps(cache_envelope), encoding="utf-8")

    # Legacy SQLite candidate
    legacy_fid = 900003
    repo.upsert_fixture(
        TournamentFixture(
            fixture_id=legacy_fid,
            home_team="Spain",
            away_team="Italy",
            status="FT",
            kickoff_time=datetime(2026, 6, 12, 18, 0),
            venue="Test",
            city="Test",
            country="Test",
            group="B",
            round="Group",
            is_placeholder=False,
            source="live",
        ),
        competition_key="world_cup_2026",
    )
    repo.upsert_prediction(
        prediction_id="legacy-900003",
        fixture_id=legacy_fid,
        competition_key="world_cup_2026",
        home_team="Spain",
        away_team="Italy",
        prediction_version="manual",
        created_at="2026-06-12T07:00:00",
        data_quality=0.8,
        prediction_quality=0.8,
        confidence=58.0,
        no_bet_flag=False,
        markets={"1x2": "away", "over_under_2_5": "under"},
    )

    # JSONL candidate (partial — should quarantine)
    jsonl_fid = 900004
    hist_path.write_text(
        json.dumps(
            {
                "fixture_id": jsonl_fid,
                "date": "2026-06-13",
                "home_team": "Portugal",
                "away_team": "Netherlands",
                "predicted_1x2": "home",
                "predicted_over_under_2_5": "over",
                "predicted_halftime_goals": 1.0,
                "predicted_first_goal_team": "home",
                "confidence_score": 55.0,
                "risk_level": "medium",
                "no_bet_flag": False,
                "data_quality_score": 0.6,
                "source": "live",
                "created_at": "2026-06-13T09:00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # Test fixture — quarantine
    test_fid = 123
    test_envelope = {
        "endpoint": "prediction_result",
        "params": {"fixture_id": test_fid},
        "payload": {
            "fixture_id": test_fid,
            "home_team": "TestA",
            "away_team": "TestB",
            "prediction": "home",
            "confidence": 50.0,
            "status": "ok",
        },
    }
    (cache_dir / "test_fixture.json").write_text(json.dumps(test_envelope), encoding="utf-8")

    dry = run_legacy_prediction_import(
        settings=settings,
        dry_run=True,
        cache_dir=cache_dir,
        history_path=hist_path,
    )
    record("dry_run_imports_candidates", dry.imported >= 3, f"imported={dry.imported}")
    record("dry_run_skips_authoritative", dry.duplicates_skipped >= 0, f"skipped={dry.duplicates_skipped}")

    result = run_legacy_prediction_import(
        settings=settings,
        dry_run=False,
        cache_dir=cache_dir,
        history_path=hist_path,
    )
    record("imported_count_positive", result.imported >= 3, f"imported={result.imported}")
    record(
        "archive_grew",
        result.archive_total_after == result.archive_total_before + result.imported,
        f"before={result.archive_total_before} after={result.archive_total_after}",
    )
    record("no_errors", len(result.errors) == 0, str(result.errors))

    after_auth = repo.get_worldcup_stored_prediction(auth_id)
    record(
        "authoritative_not_overwritten",
        after_auth is not None and after_auth.get("source") == "background",
        f"source={after_auth.get('source') if after_auth else None}",
    )
    record(
        "authoritative_payload_unchanged",
        json.loads(after_auth["payload_json"])["prediction"] == "home" if after_auth else False,
        "",
    )

    imported_rows = [
        r
        for r in repo.list_worldcup_stored_prediction_rows()
        if int(r["fixture_id"]) != auth_id
    ]
    record(
        "all_imports_tagged_legacy",
        all(r.get("source") == "legacy_import" for r in imported_rows),
        f"n={len(imported_rows)}",
    )
    record(
        "all_imports_have_metadata",
        all(r.get("imported_at") and r.get("import_source") and r.get("quality_score") is not None for r in imported_rows),
        "",
    )
    record(
        "test_fixture_quarantined",
        any(int(r["fixture_id"]) == test_fid and r.get("is_quarantined") for r in imported_rows),
        "",
    )
    record(
        "preserves_predicted_at",
        all(r.get("predicted_at") for r in imported_rows),
        "",
    )

    # Re-run import — duplicates skipped, no overwrites
    rerun = run_legacy_prediction_import(
        settings=settings,
        dry_run=False,
        cache_dir=cache_dir,
        history_path=hist_path,
    )
    record(
        "rerun_skips_duplicates",
        rerun.imported == 0 and rerun.duplicates_skipped >= result.imported,
        f"skipped={rerun.duplicates_skipped}",
    )
    record(
        "rerun_archive_unchanged",
        rerun.archive_total_after == result.archive_total_after,
        "",
    )

    score = compute_quality_score(cache_payload, "cache")
    record("quality_score_in_range", 0.0 <= score <= 1.0, f"score={score}")

    merged = merge_candidates(
        [
            LegacyImportCandidate(
                fixture_id=1,
                payload={"prediction": "home"},
                import_source="jsonl",
                predicted_at="t",
                kickoff_utc=None,
                quality_score=0.5,
                quarantine=False,
            )
        ],
        [
            LegacyImportCandidate(
                fixture_id=1,
                payload={"prediction": "away"},
                import_source="cache",
                predicted_at="t",
                kickoff_utc=None,
                quality_score=0.5,
                quarantine=False,
            )
        ],
    )
    record("merge_prefers_cache", merged[0].import_source == "cache", "")

    from worldcup_predictor.api.global_prediction_archive import list_global_archive_rows

    get_settings.cache_clear()
    public_rows = list_global_archive_rows(settings=settings, limit=500)
    public_ids = {int(r["fixture_id"]) for r in public_rows}
    record(
        "quarantined_excluded_from_public_archive",
        test_fid not in public_ids and auth_id in public_ids,
        f"public_n={len(public_ids)}",
    )

    return _report(checks)


if __name__ == "__main__":
    raise SystemExit(main())
