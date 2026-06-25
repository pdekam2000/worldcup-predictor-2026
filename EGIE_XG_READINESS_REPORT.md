# EGIE xG Readiness Report

**Phase:** 54E — Sportmonks xG Feature Store Foundation  
**Date:** 2026-06-23  
**Scope:** Readiness assessment only — no scoring changes

---

## Data foundation status

| Layer | Status |
|-------|--------|
| Sportmonks xG ingest | **READY** (normalize + cache + API) |
| PostgreSQL persistence | **READY** (`fs_sportmonks_xg_records`, `fs_sportmonks_xg_fixture_summary`) |
| Fixture summaries | **READY** |
| Rolling aggregations | **PARTIAL** (5/71 summaries with rolling xG — limited history in UEFA cache sample) |
| Player xG records | **NOT_READY** (lineups lack xGLineup in UEFA cache ingest includes) |

**Local import (UEFA cache):** 442 records, 71 fixtures, 3 leagues (CL/EL/Conference), 74 teams.

---

## EGIE target readiness

| EGIE target | Status | Rationale |
|-------------|--------|-----------|
| **First Goal Team** | **PARTIAL** | Team xG + xG difference available per fixture; rolling attack differential available when history exists. Needs WC 732 live backfill + EGIE wiring (Phase 54F). |
| **Goal Range** | **PARTIAL** | `xg_total`, `home_xg`, `away_xg`, `npxg` stored. Rolling totals need more completed fixtures per team. |
| **Goal Minute** | **NOT_READY** | xG alone insufficient; requires events/pressure store (Phase 54G). xG store does not block but does not enable minute model yet. |
| **Team Goals** | **PARTIAL** | Team-level xG/xGA/npxg metrics normalized. Ready for feature join once EGIE dataset builder consumes `fs_sportmonks_xg_fixture_summary`. |
| **Live Goal Probability** | **NOT_READY** | Requires pressure index feature store + livescores path (Phase 54G). xG store is prerequisite only. |

---

## Available features (production store)

Per-fixture summary fields:

- `home_xg`, `away_xg`, `home_xga`, `away_xga`, `home_npxg`, `away_npxg`
- `xg_total`, `xg_difference`
- `home_team_recent_xg`, `away_team_recent_xg` (rolling window=5)
- `attack_difference`, `defense_difference`, `momentum_difference`

Per-record normalized metrics (examples):

- `xg`, `xga`, `xgot`, `npxg`, `xpts`, `xg_open_play`, `xg_set_play`, `xg_corners`, `xg_free_kicks`

---

## Recommended consumption pattern (Phase 54F)

```
fs_sportmonks_xg_fixture_summary
  → EGIE dataset join on sportmonks_fixture_id / mapped api_fixture_id
  → backtest arm features: xg_diff, rolling_xg_for, rolling_xga, momentum
  → NO direct label leakage from Sportmonks predictions
```

---

## Blockers before READY across all targets

1. **WC 2026 backfill** — run `phase54e_sportmonks_xg_backfill.py --league-id 732` on server with valid token  
2. **Player xG** — re-ingest with `lineups.xGLineup.type` include  
3. **EGIE dataset join** — Phase 54F backtest arm  
4. **Goal Minute / Live probability** — Phase 54G pressure store (separate from xG)

---

## Verdict

**Overall EGIE xG readiness: PARTIAL**

The feature store foundation is in place and validated. EGIE can begin xG backtest arm work (54F) using team-level xG immediately; minute-level and live targets remain blocked on complementary stores.
