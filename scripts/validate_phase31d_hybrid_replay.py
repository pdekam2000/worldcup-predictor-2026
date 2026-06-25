#!/usr/bin/env python3
"""Phase 31D — validate hybrid replay: 0 external API calls, pipeline integrity."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.backtesting.hybrid_replay import (  # noqa: E402
    CacheOnlyApiFootballClient,
    HybridReplayStats,
    build_hybrid_intelligence_report,
    run_hybrid_replay,
    select_hybrid_replay_sample,
    _hybrid_settings,
)
from worldcup_predictor.backtesting.sqlite_historical_replay import load_finished_match_rows
from worldcup_predictor.database.repository import FootballIntelligenceRepository


def main() -> int:
    db = ROOT / "data" / "football_intelligence.db"
    if not db.exists():
        print(f"FAIL: database not found at {db}")
        return 1

    repo = FootballIntelligenceRepository(path=str(db))
    rows = load_finished_match_rows(repo)
    sample = select_hybrid_replay_sample(repo, rows, sample_size=3)
    repo.close()

    if not sample:
        print("FAIL: no finished fixtures in database")
        return 1

    settings = _hybrid_settings()
    stats = HybridReplayStats()
    client = CacheOnlyApiFootballClient(settings, stats=stats)
    repo = FootballIntelligenceRepository(path=str(db))

    checks: list[tuple[str, bool, str]] = []

    try:
        report = build_hybrid_intelligence_report(
            sample[0].fixture_id,
            repo=repo,
            api_client=client,
            settings=settings,
            competition_key=sample[0].competition,
            stats=stats,
        )
        checks.append(
            (
                "MatchIntelligenceBuilder",
                report.fixture_id == sample[0].fixture_id,
                f"fixture_id={report.fixture_id}",
            )
        )
        checks.append(
            (
                "data_quality_recomputed",
                report.data_quality is not None and report.data_quality.score is not None,
                f"score={report.data_quality.score if report.data_quality else None}",
            )
        )
    except Exception as exc:
        checks.append(("MatchIntelligenceBuilder", False, str(exc)))

    repo.close()

    result = run_hybrid_replay(db_path=str(db), sample_size=5, run_specialists=True)
    meta = result["meta"]

    checks.append(
        (
            "zero_api_football_live",
            meta["external_api_calls"] == 0,
            f"live_fetch_attempts={meta['external_api_calls']}",
        )
    )
    checks.append(
        (
            "replay_errors_zero",
            meta["errors"] == 0,
            f"errors={meta['errors']}",
        )
    )
    checks.append(
        (
            "sample_replayed",
            meta["replayed_ok"] >= 1,
            f"ok={meta['replayed_ok']}",
        )
    )

    artifact = ROOT / "artifacts" / "phase31d_hybrid_replay_summary.json"
    if artifact.exists():
        data = json.loads(artifact.read_text(encoding="utf-8"))
        checks.append(
            (
                "artifact_exists",
                data.get("meta", {}).get("phase") == "31D",
                str(artifact),
            )
        )

    failed = [c for c in checks if not c[1]]
    print("Phase 31D validation")
    print("-" * 40)
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: {detail}")

    if failed:
        print(f"\n{len(failed)} check(s) failed")
        return 1

    print("\nAll checks passed — 0 external API calls confirmed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
