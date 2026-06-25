#!/usr/bin/env python3
"""Validate Phase 54C-1 Premier League odds backfill."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT = ROOT / "artifacts" / "phase54c1_pl_odds_backfill_result.json"
MANIFEST = ROOT / "data" / "shadow" / "phase54c1_pl_odds_backfill_manifest.jsonl"
VALIDATION_ARTIFACT = ROOT / "artifacts" / "phase54c1_pl_odds_validation.json"

WC_ORPHAN_IDS = {
    900001, 900002, 900003, 900004, 900005, 900006, 900007, 900008,
    900009, 900010, 900011, 900012,
    1489369, 1489370, 1489371, 1489372, 1489373, 1489374, 1489375, 1489376,
}


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.egie.provider_features.audit import audit_egie_paid_provider_utilization
    from worldcup_predictor.egie.provider_features.store import EgieProviderFeatureStore
    from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
    from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter

    repo = FootballIntelligenceRepository(get_settings().sqlite_path or None)

    artifact = {}
    if ARTIFACT.exists():
        artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    backfill = artifact.get("backfill") or {}

    fixtures_scanned = int(backfill.get("targets") or 0)
    checks.append(_check("fixtures_scanned", fixtures_scanned > 0, f"targets={fixtures_scanned}"))

    api_calls_live = int(backfill.get("api_calls_live") or 0)
    checks.append(
        _check(
            "api_calls_documented",
            ARTIFACT.exists(),
            f"live={api_calls_live} cache={backfill.get('api_calls_cache', 0)}",
        )
    )

    snapshots_created = int(backfill.get("odds_snapshots_created") or 0)
    checks.append(
        _check("odds_snapshots_inserted", snapshots_created > 0, f"created={snapshots_created}")
    )

    pl_fixture_ids = [
        int(r[0])
        for r in repo._conn.execute(
            """
            SELECT fixture_id FROM fixtures
            WHERE competition_key = 'premier_league' AND is_placeholder = 0
              AND status IN ('FT','AET','PEN','FINISHED','AWD','WO')
            """
        ).fetchall()
    ]
    store = EgieProviderFeatureStore()
    parseable = 0
    for fid in pl_fixture_ids:
        vec = store.build(fid, competition_key="premier_league")
        if vec.coverage.get("odds") and vec.odds_implied_home is not None:
            parseable += 1
    parseable_pct = round(100 * parseable / len(pl_fixture_ids), 2) if pl_fixture_ids else 0.0
    checks.append(
        _check(
            "parseable_1x2_odds",
            parseable >= 350,
            f"parseable={parseable}/{len(pl_fixture_ids)} ({parseable_pct}%)",
        )
    )

    pl_odds_after = int(
        repo._conn.execute(
            """
            SELECT COUNT(DISTINCT o.fixture_id)
            FROM odds_snapshots o
            JOIN fixtures f ON f.fixture_id = o.fixture_id
            WHERE f.competition_key = 'premier_league' AND f.is_placeholder = 0
            """
        ).fetchone()[0]
        or 0
    )
    pl_odds_before = int(backfill.get("pl_odds_fixtures_before") or 0)
    checks.append(
        _check(
            "pl_coverage_after",
            pl_odds_after >= 350,
            f"before={pl_odds_before} after={pl_odds_after}",
        )
    )

    audit = audit_egie_paid_provider_utilization(competition_key="premier_league", limit=400)
    cov = (audit.get("provider_feature_store") or {}).get("coverage_pct") or {}
    cov_before = (
        (artifact.get("utilization_before") or {}).get("provider_feature_store") or {}
    ).get("coverage_pct", {}).get("odds", 0)
    cov_after = cov.get("odds", 0)
    checks.append(
        _check(
            "egie_odds_coverage_after",
            float(cov_after) > 50,
            f"before={cov_before}% after={cov_after}%",
        )
    )

    stored = StoredGoalTimingAdapter()
    fb = GoalTimingFeatureBuilder(stored=stored, max_api_event_fetches=0)
    sample_ids = pl_fixture_ids[: min(50, len(pl_fixture_ids))]
    reliable = 0
    for fid in sample_ids:
        feats = fb.build(fid, competition_key="premier_league")
        if feats.get("has_reliable_goal_odds"):
            reliable += 1
    reliable_pct = round(100 * reliable / len(sample_ids), 2) if sample_ids else 0.0
    checks.append(
        _check(
            "goal_timing_has_reliable_goal_odds",
            reliable_pct > 50,
            f"sample={reliable}/{len(sample_ids)} ({reliable_pct}%)",
        )
    )
    checks.append(
        _check(
            "has_reliable_goal_odds_status",
            reliable > 0,
            f"reliable_count={reliable}",
        )
    )

    wc_contaminated = repo._conn.execute(
        """
        SELECT COUNT(*) FROM odds_snapshots o
        WHERE o.competition_key = 'premier_league'
          AND o.fixture_id IN ({})
        """.format(",".join("?" * len(WC_ORPHAN_IDS))),
        list(WC_ORPHAN_IDS),
    ).fetchone()[0]
    checks.append(
        _check(
            "no_world_cup_contamination",
            int(wc_contaminated or 0) == 0,
            f"wc_ids_in_pl_competition_key={wc_contaminated}",
        )
    )

    dup_rows = repo._conn.execute(
        """
        SELECT o.fixture_id, COUNT(*) AS n
        FROM odds_snapshots o
        JOIN fixtures f ON f.fixture_id = o.fixture_id
        WHERE f.competition_key = 'premier_league'
        GROUP BY o.fixture_id
        HAVING n > 3
        """
    ).fetchall()
    checks.append(
        _check(
            "no_duplicate_snapshot_explosion",
            len(dup_rows) == 0,
            f"fixtures_with_gt3_snapshots={len(dup_rows)}",
        )
    )

    wc_preserved = repo._conn.execute(
        """
        SELECT COUNT(*) FROM odds_snapshots o
        WHERE o.fixture_id IN ({})
        """.format(",".join("?" * len(WC_ORPHAN_IDS))),
        list(WC_ORPHAN_IDS),
    ).fetchone()[0]
    checks.append(
        _check(
            "world_cup_rows_preserved",
            int(wc_preserved or 0) > 0,
            f"wc_orphan_snapshot_rows={wc_preserved}",
        )
    )

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks)
    summary = {
        "passed": passed,
        "total": total,
        "all_pass": passed == total,
        "checks": checks,
        "metrics": {
            "fixtures_scanned": fixtures_scanned,
            "api_calls_live": api_calls_live,
            "snapshots_created": snapshots_created,
            "pl_odds_before": pl_odds_before,
            "pl_odds_after": pl_odds_after,
            "parseable_1x2": parseable,
            "egie_odds_coverage_before_pct": cov_before,
            "egie_odds_coverage_after_pct": cov_after,
            "goal_timing_reliable_sample_pct": reliable_pct,
        },
    }

    VALIDATION_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_ARTIFACT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"VALIDATION: {passed}/{total} PASS")
    for c in checks:
        status = "PASS" if c["pass"] else "FAIL"
        print(f"  [{status}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
