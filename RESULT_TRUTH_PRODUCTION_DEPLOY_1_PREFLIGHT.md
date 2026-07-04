# RESULT-TRUTH-PRODUCTION-DEPLOY-1 — Preflight

**Phase:** RESULT-TRUTH-PRODUCTION-DEPLOY-1  
**Timestamp:** 2026-07-04 (UTC)  
**Host:** root@91.107.188.229  
**Path:** `/opt/worldcup-predictor`

---

## Part A — Three-Way Source State

| Source | HEAD | Synced with origin/main? |
|--------|------|--------------------------|
| **LOCAL** | `282ef700f7bc31090f775f752f168d30e701ba24` | Yes (same commit) |
| **GITHUB MAIN** | `282ef700f7bc31090f775f752f168d30e701ba24` | — |
| **HETZNER** | `282ef700f7bc31090f775f752f168d30e701ba24` | Yes (same commit) |

**Commit message:** `282ef70 fix(odds): pass season when building DailyFixture for single-fixture refresh`

### Code availability

All three environments share the same **git commit**, but **RESULT-TRUTH-REPAIR-1 code is not on that commit**. It exists only as **uncommitted local changes** on the developer machine:

| File | Status |
|------|--------|
| `worldcup_predictor/database/schema.py` | Modified (SCHEMA v8) |
| `worldcup_predictor/database/migrations.py` | Modified |
| `worldcup_predictor/database/repository.py` | Modified |
| `worldcup_predictor/research/ecse_live/result_sync.py` | Modified |
| `worldcup_predictor/api/prediction_history_evaluation.py` | Modified |
| `worldcup_predictor/outcomes/provider_score_truth.py` | **Untracked** |
| `worldcup_predictor/outcomes/market_result_resolver.py` | **Untracked** |
| `worldcup_predictor/owner/owner_tracker_builder.py` | **Untracked** |
| `scripts/run_result_truth_repair_1.py` | **Untracked** |
| `scripts/validate_result_truth_repair_1.py` | **Untracked** |

**Verdict:** `CODE_SYNC_REQUIRED_BEFORE_RESULT_DEPLOY` — deploy halted per task rules.

---

## Part B — Production Git Working Tree

- Branch: `main...origin/main` (no commit drift)
- Extensive **local modifications** on Hetzner (data dumps, shadow JSONL, validation files) — runtime/data drift only, not source-code drift
- No tracked Python source files modified on Hetzner for RESULT-TRUTH modules (modules absent entirely)

---

## Part B — Services

| Service | Status |
|---------|--------|
| `worldcup-api` | **active** |
| `nginx` | **active** |
| `/api/health` | **HTTP 200** |

---

## Part B — Canonical SQLite DB

| Property | Value |
|----------|-------|
| Path | `/opt/worldcup-predictor/data/football_intelligence.db` |
| Size | 10,123,419,648 bytes (~9.4 GiB) |
| Schema version | **7** |
| `fixture_results` row count | **1,930** |
| Regulation columns (`regulation_home_goals`, etc.) | **Absent** |
| Schema v8 columns | **Not present** |

### Target 11-match knockout coverage (Jul 1–4 batch)

| Fixture ID | Match | Fixture in DB | Result in DB | Notes |
|------------|-------|---------------|--------------|-------|
| 1567306 | Mexico vs Ecuador | No | No | Missing |
| 1567307 | England vs DR Congo | No | No | Missing |
| 1567308 | Belgium vs Senegal | No | No | Missing (AET regression) |
| 1562586 | USA vs Bosnia | No | No | Missing |
| 1567311 | Spain vs Austria | No | No | Missing |
| 1567309 | Portugal vs Croatia | No | No | Missing |
| 1567312 | Switzerland vs Algeria | No | No | Missing |
| 1565178 | Australia vs Egypt | No | No | Missing (PEN regression) |
| 1565179 | Argentina vs Cape Verde | No | No | Missing (AET regression) |
| 1567310 | Colombia vs Ghana | Yes (FT) | Yes (1-0) | Present |
| 1567824 | Canada vs Morocco | Yes (**1H**) | No | Fixture stale; result not synced |

**Coverage summary:** 2/11 fixtures present; 1/11 with finished result; **9 fixtures entirely absent**.

---

## Parts C–K — Not Executed

The following steps were **not run** because Part A blocked deployment:

- C — Production DB backup (pre schema v8)
- D — `git pull` deploy (would be no-op; code not pushed)
- E — Schema v8 migration
- F — Controlled result sync (`run_result_truth_repair_1.py`)
- G — AET/PEN regression verification on production
- H — Owner tracker rebuild from production DB
- I — Production canonical 11-match scorecard
- J — Hash integrity check on production
- K — Service restart / extended smoke tests

---

## Required Next Step

1. **Commit and push** RESULT-TRUTH-REPAIR-1 code to `origin/main` (minimum files listed above).
2. Re-run **RESULT-TRUTH-PRODUCTION-DEPLOY-1** from Part B onward.

Do **not** manually SCP uncommitted code or copy the local SQLite DB to production.
