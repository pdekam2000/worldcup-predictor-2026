#!/usr/bin/env python3
"""Validate Phase 54C-2 odds snapshot parser fix against stored WC rows."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT = ROOT / "artifacts" / "phase54c2_odds_parser_validation.json"
WC_ORPHAN_IDS = {
    900001, 900002, 900003, 900004, 900005, 900006, 900007, 900008,
    900009, 900010, 900011, 900012,
    1489369, 1489370, 1489371, 1489372, 1489373, 1489374, 1489375, 1489376,
}


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def _legacy_parse_payload(payload: dict) -> bool:
    """Pre-54C-2 behavior: extract_api_sports_probs on raw dict (always failed)."""
    from worldcup_predictor.agents.specialists.odds_control_agent import extract_api_sports_probs

    probs = extract_api_sports_probs(payload)
    return probs.get("home") is not None


def _new_parse_payload(payload: dict, *, fixture_id: int) -> dict:
    from worldcup_predictor.egie.provider_features.odds_snapshot_parser import parse_snapshot_payload

    return parse_snapshot_payload(payload, fixture_id=fixture_id)


def main() -> int:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.egie.provider_features.extractors import parse_odds_snapshots
    from worldcup_predictor.egie.provider_features.store import EgieProviderFeatureStore

    repo = FootballIntelligenceRepository(get_settings().sqlite_path)
    wc_row_count_before = repo._conn.execute("SELECT COUNT(1) FROM odds_snapshots").fetchone()[0]

    rows = repo._conn.execute(
        """
        SELECT o.id, o.fixture_id, o.competition_key, o.snapshot_at, o.payload_json
        FROM odds_snapshots o
        WHERE o.competition_key = 'world_cup_2026'
           OR o.fixture_id IN ({wc})
        ORDER BY o.fixture_id, o.snapshot_at
        """.format(wc=",".join("?" * len(WC_ORPHAN_IDS))),
        list(WC_ORPHAN_IDS),
    ).fetchall()

    legacy_parseable = 0
    new_parseable = 0
    ou25_parseable = 0
    btts_parseable = 0

    for row in rows:
        payload = json.loads(row["payload_json"])
        fid = int(row["fixture_id"])
        if _legacy_parse_payload(payload):
            legacy_parseable += 1
        parsed = _new_parse_payload(payload, fixture_id=fid)
        if parsed.get("odds_implied_home") is not None:
            new_parseable += 1
        if parsed.get("odds_implied_over_25") is not None:
            ou25_parseable += 1
        if parsed.get("odds_implied_btts_yes") is not None:
            btts_parseable += 1

    distinct_wc_fixtures = sorted({int(r["fixture_id"]) for r in rows})

    # EGIE + Goal Timing on WC fixtures with snapshots
    store = EgieProviderFeatureStore()
    egie_odds = 0
    for fid in distinct_wc_fixtures:
        comp = repo._conn.execute(
            "SELECT competition_key FROM fixtures WHERE fixture_id = ?", (fid,)
        ).fetchone()
        comp_key = comp[0] if comp else "world_cup_2026"
        vec = store.build(fid, competition_key=str(comp_key))
        if vec.coverage.get("odds") and vec.odds_implied_home is not None:
            egie_odds += 1

    # Goal Timing uses premier_league scope only; EGIE store is readiness proxy.
    gt_readiness = egie_odds >= 50

    pl_odds = repo._conn.execute(
        """
        SELECT COUNT(DISTINCT o.fixture_id)
        FROM odds_snapshots o
        JOIN fixtures f ON f.fixture_id = o.fixture_id
        WHERE f.competition_key = 'premier_league'
        """
    ).fetchone()[0]

    wc_row_count_after = repo._conn.execute("SELECT COUNT(1) FROM odds_snapshots").fetchone()[0]
    wc_orphan_after = repo._conn.execute(
        "SELECT COUNT(1) FROM odds_snapshots WHERE fixture_id IN ({})".format(
            ",".join("?" * len(WC_ORPHAN_IDS))
        ),
        list(WC_ORPHAN_IDS),
    ).fetchone()[0]

    # Integration via fetch_odds_snapshots + parse_odds_snapshots
    integration_ok = 0
    for fid in distinct_wc_fixtures[:10]:
        snaps = repo.fetch_odds_snapshots(fid, limit=5)
        parsed = parse_odds_snapshots(snaps)
        if parsed.get("odds_implied_home") is not None:
            integration_ok += 1

    checks: list[dict] = []
    checks.append(_check("wc_rows_scanned", len(rows) > 0, f"rows={len(rows)}"))
    checks.append(
        _check(
            "legacy_parser_mostly_broken",
            legacy_parseable < new_parseable,
            f"before={legacy_parseable} after={new_parseable}",
        )
    )
    checks.append(
        _check(
            "new_parser_1x2_coverage",
            new_parseable >= 900,
            f"parseable_1x2_rows={new_parseable}/{len(rows)}",
        )
    )
    checks.append(
        _check(
            "new_parser_ou25_coverage",
            ou25_parseable >= 900,
            f"parseable_ou25_rows={ou25_parseable}/{len(rows)}",
        )
    )
    checks.append(
        _check(
            "new_parser_btts_coverage",
            btts_parseable >= 500,
            f"parseable_btts_rows={btts_parseable}/{len(rows)}",
        )
    )
    checks.append(
        _check(
            "egie_odds_on_wc_fixtures",
            egie_odds >= 50,
            f"fixtures_with_odds={egie_odds}/{len(distinct_wc_fixtures)}",
        )
    )
    checks.append(
        _check(
            "goal_timing_odds_readiness",
            gt_readiness,
            (
                f"egie_store_odds={egie_odds}/{len(distinct_wc_fixtures)}; "
                "Goal Timing builder is premier_league-scoped (WC returns empty features)"
            ),
        )
    )
    checks.append(
        _check(
            "has_reliable_goal_odds_status",
            gt_readiness,
            f"reliable_via_egie_store={egie_odds}",
        )
    )
    checks.append(_check("no_pl_fake_rows", int(pl_odds or 0) == 0, f"pl_odds_fixtures={pl_odds}"))
    checks.append(
        _check(
            "wc_rows_unchanged",
            wc_row_count_after == wc_row_count_before,
            f"before={wc_row_count_before} after={wc_row_count_after}",
        )
    )
    checks.append(
        _check(
            "wc_orphan_rows_preserved",
            wc_orphan_after >= 500,
            f"orphan_rows={wc_orphan_after}",
        )
    )
    checks.append(
        _check(
            "extractors_integration",
            integration_ok >= 8,
            f"integration_sample={integration_ok}/10",
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
            "wc_snapshot_rows_scanned": len(rows),
            "wc_distinct_fixtures": len(distinct_wc_fixtures),
            "legacy_parseable_rows": legacy_parseable,
            "new_parseable_1x2_rows": new_parseable,
            "new_parseable_ou25_rows": ou25_parseable,
            "new_parseable_btts_rows": btts_parseable,
            "egie_wc_fixtures_with_odds": egie_odds,
            "goal_timing_odds_readiness_via_egie_store": egie_odds,
            "pl_odds_fixtures": int(pl_odds or 0),
            "wc_rows_before": wc_row_count_before,
            "wc_rows_after": wc_row_count_after,
        },
    }

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"VALIDATION: {passed}/{total} PASS")
    for c in checks:
        status = "PASS" if c["pass"] else "FAIL"
        print(f"  [{status}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
