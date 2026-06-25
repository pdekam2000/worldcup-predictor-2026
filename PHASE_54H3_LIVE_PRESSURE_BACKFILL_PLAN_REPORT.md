# PHASE 54H-3 — Live Pressure API Backfill Plan Report

**Phase:** 54H-3 (plan + safe access test only)  
**Status:** COMPLETE  
**Validation:** 9/9 PASS  
**Generated:** 2026-06-24  

---

## Executive summary

Phase 54H-3 prepared a safe Sportmonks pressure backfill plan with **no mass import**. Key outcomes:

| Check | Result |
|-------|--------|
| Server token | **OK** — present, length 60, `include=pressure` returns 196 rows on fixture 19135063 |
| Local token | **FAIL** — HTTP 401 Invalid token |
| Target candidates | **1,519** fixtures not yet in pressure store |
| Min backfill API calls | **~90** (100-fixture target) |
| Quota risk | **LOW** for minimum run |
| Go/no-go | **`READY_FOR_PRESSURE_BACKFILL`** (execute on **server** only) |

Do **not** run large backfill locally until token is synced. Do **not** resume pressure modeling until coverage ≥150 fixtures post-backfill.

---

## 1. Token readiness

| Scope | Present | Length | Pressure probe | Rows | Verdict |
|-------|---------|--------|----------------|------|---------|
| **Server** (`/opt/worldcup-predictor/.env.production`) | Yes | 60 | HTTP **200** | **196** | **OK** |
| **Local** (`.env`) | Yes | 60 | HTTP **401** | 0 | **FAIL** |

- No tokens printed in logs or artifacts.
- Server probe: `GET /fixtures/19135063?include=participants;pressure` → success.
- Local token is **stale/invalid** — copy from server `.env.production` before local API work.

---

## 2. Small live test results

### Server (5 live API calls — within budget)

| Label | Fixture ID | HTTP | Pressure rows | Notes |
|-------|------------|------|---------------|-------|
| Champions League | 1058477 | 200 | 0 | Old-season ID; API returns empty pressure |
| Europa League | 1059951 | 200 | 0 | Old-season ID |
| Conference League | 18151405 | 200 | 0 | Old-season ID |
| World Cup | 19609127 | 200 | **202** | Pressure confirmed for WC |
| Control (invalid ID) | 99999999 | 200 | 0 | Empty payload |

**Token validation fixture:** 19135063 → HTTP 200, **196 rows**, minute coverage present.

### Local (5 calls — all failed)

All probes returned HTTP **401** (invalid token). No cache saved locally.

**Artifact:** `artifacts/phase54h3_live_pressure_backfill_plan/server_live_probes.json`

**Implication:** Prioritize **recent completed fixtures** (2024–25 UEFA IDs in target list) — older cache IDs may not return pressure via API even with valid token.

---

## 3. Target fixture design

| League | ID | Candidates (not imported) |
|--------|-----|----------------------------|
| Champions League | 2 | 540 |
| Europa League | 5 | 518 |
| Conference League | 2286 | 414 |
| World Cup | 732 | 47 |
| **Total** | | **1,519** |

**Already imported:** 65 fixtures

**Prioritization:** finished fixtures → with events → with xG hint → not in pressure cache

**Target lists:**
- Minimum next run: **100** fixture IDs
- Preferred: **300** fixture IDs

Sample probe IDs per league: CL `1058472`, EL `19135827`, Conference `18151401`, WC `19609127`

**Artifact:** `artifacts/phase54h3_live_pressure_backfill_plan/plan.json` → `target_design`

---

## 4. API call estimate

| Run | Fixtures | UEFA cache hits | API calls required | Est. pressure rows |
|-----|----------|-----------------|--------------------|--------------------|
| Minimum (100 new) | 100 | 10 | **90** | ~17,550 |
| Preferred (300 new) | 300 | 10 | **290** | ~52,650 |

- Assumes ~195 rows/fixture (from current store average).
- Discovery pagination may add **1–4 calls per league** if fixture lists are not cached.
- **Already imported:** 65 (skipped via manifest / `--skip-existing`).

---

## 5. Quota risk

| Scenario | Calls | Risk |
|----------|-------|------|
| Minimum 100-fixture run | ~90–100 | **LOW** |
| Preferred 300-fixture run | ~290–310 | **MEDIUM** |
| Full 1,519 candidates | ~1,500+ | **HIGH** — do not run in one batch |

---

## 6. Backfill command proposal

**Run on server only** (valid token):

```bash
cd /opt/worldcup-predictor
set -a && source .env.production && set +a

# Dry-run first (no API spend beyond discovery if cached)
python3 scripts/phase54h_pressure_feature_store_backfill.py \
  --league-id 2 --max-calls 25 --dry-run --cache-first --skip-existing --resume

# Minimum expansion tranche (repeat per league 2, 5, 2286, 732)
python3 scripts/phase54h_pressure_feature_store_backfill.py \
  --league-id 2 --max-calls 30 --cache-first --skip-existing --save-raw \
  --job-key phase54h3_cl_batch1

# Or plan-only estimate locally/server:
python3 scripts/phase54h_pressure_feature_store_backfill.py --plan-only
```

**Hardened CLI flags (Part E):**
- `--league-id`, `--season-id`, `--max-calls`
- `--cache-first` / `--no-cache`
- `--skip-existing` / `--no-skip-existing`
- `--save-raw`, `--dry-run`, `--job-key`, `--resume`
- `--fixture-id` (single-fixture test)
- `--plan-only`
- Pressure include is always `participants;pressure;events.type` in store layer

---

## 7. Go / no-go decision

### **`READY_FOR_PRESSURE_BACKFILL`** (server execution)

| Gate | Status |
|------|--------|
| Server token + pressure include | ✅ PASS |
| Local token | ❌ Sync required for local runs |
| Target list designed | ✅ 1,519 candidates |
| Call estimate documented | ✅ ~90 for 100 fixtures |
| Mass backfill executed | ❌ **Not run** (per phase scope) |
| Pressure modeling | ❌ **Blocked** until post-backfill coverage ≥150 |

### Action items before Phase 54H-4 (backfill execution)

1. Sync `SPORTMONKS_API_TOKEN` from server to local `.env` (optional).
2. Deploy latest `phase54h_pressure_feature_store_backfill.py` + pressure store to server.
3. Run **dry-run** then **30-call batches** per league on server.
4. Verify pressure store count ≥150 before any modeling restart.
5. Filter target list to **recent seasons** — skip legacy IDs that return zero pressure rows.

---

## Safety compliance

| Rule | Status |
|------|--------|
| No production prediction changes | ✅ |
| No WDE / SaaS / deploy | ✅ |
| No mass backfill | ✅ (5 server + 5 local probe calls only) |
| No token in logs/artifacts | ✅ |

---

## Module map

| Component | Path |
|-----------|------|
| Backfill plan engine | `worldcup_predictor/feature_store/pressure_store/backfill_plan.py` |
| Orchestrator | `scripts/phase54h3_live_pressure_backfill_plan.py` |
| Server probe | `scripts/_phase54h3_server_probe_run.sh` |
| Server live probes | `scripts/_phase54h3_server_live_probes.sh` |
| Hardened backfill CLI | `scripts/phase54h_pressure_feature_store_backfill.py` |
| Validation | `scripts/validate_phase54h3_live_pressure_backfill_plan.py` |

---

**STOP** — Phase 54H-3 complete. No full backfill. No deploy. No live prediction changes.
