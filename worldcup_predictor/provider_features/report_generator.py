"""Generate prematch feature phase documentation."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.provider_features.entitlements import verify_entitlements
from worldcup_predictor.provider_features.mapping import OWNER_SCOPE_MATRIX_KEYS, competition_meta
from worldcup_predictor.provider_features.repository import ensure_tables


def _fixture_counts(conn: sqlite3.Connection, key: str) -> dict[str, int]:
    total = int(conn.execute("SELECT COUNT(*) FROM fixtures WHERE competition_key=?", (key,)).fetchone()[0])
    completed = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM fixtures f
            JOIN fixture_results r ON r.fixture_id=f.fixture_id
            WHERE f.competition_key=?
            """,
            (key,),
        ).fetchone()[0]
    )
    future = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM fixtures
            WHERE competition_key=? AND status IN ('NS','TBD','SCHEDULED','TIMED')
            AND datetime(kickoff_utc) > datetime('now')
            """,
            (key,),
        ).fetchone()[0]
    )
    odds = int(
        conn.execute(
            """
            SELECT COUNT(DISTINCT o.fixture_id) FROM odds_snapshots o
            JOIN fixtures f ON f.fixture_id=o.fixture_id
            WHERE f.competition_key=?
            """,
            (key,),
        ).fetchone()[0]
    )
    enr = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM fixture_enrichment e
            JOIN fixtures f ON f.fixture_id=e.fixture_id
            WHERE f.competition_key=?
            """,
            (key,),
        ).fetchone()[0]
    )
    prematch = int(
        conn.execute(
            "SELECT COUNT(DISTINCT fixture_id) FROM prematch_feature_snapshots WHERE competition_key=?",
            (key,),
        ).fetchone()[0]
    )
    return {
        "total": total,
        "completed": completed,
        "future": future,
        "with_odds": odds,
        "with_enrichment": enr,
        "with_prematch_snapshots": prematch,
    }


def generate_coverage_target_matrix() -> str:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    ensure_tables(conn)
    lines = [
        "# Prematch Feature Coverage Target Matrix",
        "",
        "| Competition | Tier | API-FB league | SM xG | Fixtures | Completed | Future | Odds | Enrichment | Prematch snaps | Priority |",
        "|-------------|------|---------------|-------|----------|-----------|--------|------|------------|----------------|----------|",
    ]
    priority_map = {
        "world_cup_2026": 1,
        "allsvenskan": 2,
        "eliteserien": 2,
        "superettan": 3,
        "veikkausliiga": 3,
        "a_lyga": 4,
        "virsliga": 4,
        "urvalsdeild": 4,
    }
    for key in OWNER_SCOPE_MATRIX_KEYS:
        meta = competition_meta(key)
        counts = _fixture_counts(conn, key)
        lines.append(
            f"| {key} | {meta.get('tier')} | {meta.get('provider_league_id')} | "
            f"{'yes' if meta.get('sportmonks_xg_supported') else 'no'} | {counts['total']} | "
            f"{counts['completed']} | {counts['future']} | {counts['with_odds']} | "
            f"{counts['with_enrichment']} | {counts['with_prematch_snapshots']} | P{priority_map.get(key, 5)} |"
        )
    conn.close()
    lines.extend(
        [
            "",
            "Pilot selections: `world_cup_2026`, `allsvenskan`, `eliteserien`.",
            "Tier B domestic leagues: API-Football only (no SportMonks mapping).",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_entitlement_report() -> str:
    ent = verify_entitlements(dry_run=True)
    lines = ["# Prematch Feature Provider Entitlement Report", "", f"Verified (dry): {ent.get('verified_at_utc')}", ""]
    for feat, cls in (ent.get("feature_classification") or {}).items():
        lines.append(f"- **{feat}**: `{cls}`")
    lines.extend(
        [
            "",
            "## SportMonks limitation",
            "",
            "SportMonks enrichment is wired for **World Cup 2026 only** (league 732, season 26618).",
            "Tier B domestic competitions have **no SportMonks prematch xG mapping** in codebase.",
            "",
            "Classification: `SPORTMONKS_PREMATCH_XG_NOT_AVAILABLE` for Tier B.",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_final_report(run_summary: dict[str, Any] | None = None) -> str:
    path = Path("artifacts/prematch_feature_backfill/run_summary.json")
    data = run_summary or (json.loads(path.read_text(encoding="utf-8")) if path.exists() else {})
    pilot = (data.get("steps") or {}).get("pilot_backfill") or {}
    cov = (data.get("steps") or {}).get("coverage") or {}
    status = "PREMATCH_FEATURE_BACKFILL_PARTIAL_PROVIDER_LIMITED"
    if pilot.get("status") == "ok" and pilot.get("snapshots_inserted", 0) > 0:
        status = "PREMATCH_FEATURE_PILOT_BACKFILL_COMPLETE"
    if not pilot.get("snapshots_inserted") and pilot.get("fixtures_targeted", 0) > 0:
        status = "PREMATCH_FEATURE_BACKFILL_PARTIAL_PROVIDER_LIMITED"
    sm_xg_tier_b = "SPORTMONKS_PREMATCH_XG_NOT_AVAILABLE for Tier B"
    return f"""# Prematch Feature Coverage Backfill Report

## Final status

**{status}**

---

## Answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Historical prematch xG providers? | SportMonks xGFixture (WC only); Tier B: not mapped |
| 2 | SportMonks defensible timestamp? | Only for live/upcoming fetches; historical xG lacks publication time |
| 3 | Competitions covered? | Pilot: world_cup_2026, allsvenskan, eliteserien |
| 4 | Lineup historically timestamped? | Via `fixture_enrichment.updated_at` when < kickoff |
| 5 | Injury historically timestamped? | Future-snapshot-only for live; historical requires provenance |
| 6 | Future-snapshot-only? | Injury/lineup for upcoming live fetches |
| 7 | Pilot fixtures targeted? | {pilot.get('fixtures_targeted', 'n/a')} |
| 8 | Snapshots stored? | inserted={pilot.get('snapshots_inserted')}, duplicate={pilot.get('snapshots_duplicate')} |
| 9 | API calls used? | API-FB={pilot.get('api_calls_used', 0)}, SM={pilot.get('sportmonks_calls_used', 0)} |
| 10 | xG coverage before/after | See coverage_before/after in run_summary.json |
| 11 | Lineup coverage before/after | See `feature_families.lineup` in coverage artifact |
| 12 | Injury coverage before/after | See `feature_families.injury` |
| 13 | Leakage rejected rows? | {pilot.get('snapshots_rejected', 0)} |
| 14 | Post-match admitted? | No — POST_MATCH rows rejected at insert |
| 15 | Immutable/idempotent? | Yes — `INSERT OR IGNORE` on snapshot_key |
| 16 | Provenance recorded? | Yes — provider, endpoint, timestamps, leakage_status |
| 17 | Missingness explicit? | Yes — completeness_mask JSON |
| 18 | 30-day shadow runner ready? | Manifest at `data/shadow/provider_feature_fusion_live/manifest.json` |
| 19 | Production prediction changed? | **No** |
| 20 | Shadow promoted? | **No** |
| 21 | Regressions passing? | Run validate_prematch_feature_coverage_backfill.py |
| 22 | Local=Origin=Production? | After commit/push |
| 23 | Next phase? | 30-day live shadow with timer approval; SportMonks Tier B mapping if licensed |

**Note:** {sm_xg_tier_b}

**STOP** — No timer enabled. No production promotion.
"""


def generate_all_reports() -> dict[str, str]:
    mapping = {
        "PREMATCH_FEATURE_COVERAGE_TARGET_MATRIX.md": generate_coverage_target_matrix(),
        "PREMATCH_FEATURE_PROVIDER_ENTITLEMENT_REPORT.md": generate_entitlement_report(),
        "PREMATCH_FEATURE_SNAPSHOT_SEMANTICS.md": _semantics_doc(),
        "PREMATCH_FEATURE_BACKFILL_FEASIBILITY.md": _feasibility_doc(),
        "PREMATCH_FEATURE_BACKFILL_CALL_PLAN.md": _call_plan_doc(),
        "XG_FEATURE_TEMPORAL_POLICY.md": _xg_policy_doc(),
        "PREMATCH_FEATURE_PILOT_COVERAGE_REPORT.md": _pilot_coverage_doc(),
        "PREMATCH_FEATURE_LIVE_SHADOW_SCHEDULE_DESIGN.md": _schedule_doc(),
        "PREMATCH_FEATURE_COVERAGE_BACKFILL_REPORT.md": generate_final_report(),
    }
    for name, content in mapping.items():
        Path(name).write_text(content, encoding="utf-8")
    return {k: k for k in mapping}


def _semantics_doc() -> str:
    return """# Prematch Feature Snapshot Semantics

Required condition: `feature_available_at_utc <= prediction_cutoff_utc < kickoff_utc`

| Field | Semantics |
|-------|-----------|
| feature_available_at_utc | Provider publication or verified enrichment update time |
| fetched_at_utc | Ingest time (always set) |
| prediction_cutoff_utc | Default T-3h before kickoff |
| leakage_status | SAFE_PREMATCH, FUTURE_SNAPSHOT_ONLY, POST_MATCH_ONLY, REJECTED |

Historical rows without defensible availability timestamp remain non-promotable.
"""


def _feasibility_doc() -> str:
    return """# Prematch Feature Backfill Feasibility

| Family | Classification | Notes |
|--------|----------------|-------|
| xG (SportMonks) | FUTURE_SNAPSHOT_ONLY (WC) / NOT_AVAILABLE (Tier B) | No domestic SM mapping |
| lineup | HISTORICAL_PARTIAL_SAFE | enrichment.updated_at < kickoff |
| injury | FUTURE_SNAPSHOT_ONLY | Live API for upcoming |
| form | HISTORICAL_PREMATCH_SAFE | API-Football team stats with cutoff |
| standings | HISTORICAL_PREMATCH_SAFE | Prior matchday only |
| pressure | LIVE_ONLY | Not for prematch backfill |
| referee | HISTORICAL_PARTIAL_SAFE | OddAlerts CSV where mapped |
"""


def _call_plan_doc() -> str:
    return """# Prematch Feature Backfill Call Plan

## Staged budgets (pilot)

| Provider | Cap | Usage |
|----------|-----|-------|
| API-Football | 50 | Lineups + injuries for upcoming pilot fixtures |
| SportMonks | 50 | WC xGFixture probes only |

## Dry-run estimate (pilot)

- ~45 fixtures targeted (15 × 3 competitions)
- Stored enrichment: 0 API calls (completed lineup from DB)
- Upcoming: up to 2 calls/fixture (lineups + injuries)
- Cache-first via existing `api_response_cache`

**Approval required before exceeding caps.**
"""


def _xg_policy_doc() -> str:
    return """# xG Feature Temporal Policy

1. **Historical realized match xG** — POST_MATCH_ONLY, never in prematch store
2. **Rolling team xG prior** — SAFE if source fixture kickoff < target kickoff
3. **Provider prematch xG** — SAFE only with valid availability timestamp (WC SportMonks live)
4. **Target match realized xG** — EXCLUDED always

Do not use CSV `expectedGoalsHome` as prematch feature.
"""


def _pilot_coverage_doc() -> str:
    path = Path("artifacts/prematch_feature_backfill/run_summary.json")
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        cov = (data.get("steps") or {}).get("coverage") or {}
        return "# Prematch Feature Pilot Coverage Report\n\n```json\n" + json.dumps(cov, indent=2) + "\n```\n"
    return "# Prematch Feature Pilot Coverage Report\n\nPending pilot run.\n"


def _schedule_doc() -> str:
    return """# Prematch Feature Live Shadow Schedule Design

**Not enabled — design only.**

| Checkpoint | Action |
|------------|--------|
| T-24h | Initial prematch snapshot collection |
| T-6h | Update snapshot |
| T-1h | Update snapshot |
| T-30m | Final freeze for shadow prediction |
| Post-kickoff | No prematch record update |

Quota: reuse odds timer cadence awareness; separate approval for feature snapshot timer.
"""
