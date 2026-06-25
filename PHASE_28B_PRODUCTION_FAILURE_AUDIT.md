# Phase 28B Production Failure Audit

**Date:** 2026-06-20  
**Endpoint:** `POST /api/predict/1539007`  
**Status:** Audit complete — **no deploy, no production changes made during this audit**

---

## Executive Summary

**Root cause:** Filesystem permission mismatch — `worldcup-api` runs as `www-data`, but cache/data files under `.cache/` and `data/` were created or overwritten by **`root`** during manual SSH validation. When the predict pipeline tries to **write** the expected-lineup cache, it raises `PermissionError`, which is caught as a generic 500: *"Failed to run prediction pipeline."*

**Phase 28B is not the direct code defect.** Rollback to `1556fc0` was already attempted on production and **did not fix** the failure. Rollback to `6fb9fec` is **not required** and would not address the underlying issue.

**Safest recovery:** Fix ownership/permissions on cache and data directories (ops), then re-test predict. Optional code hardening to fail-soft on cache write errors.

---

## Exact Exception

```
PermissionError: [Errno 13] Permission denied:
  '.cache/api_football/lineups/7c1712a8f440bb4c159ef347535361b3a401d8d19a2963e68d082398f82e2074.json'
```

### Full traceback (from `journalctl -u worldcup-api`, 2026-06-20 11:53:28 UTC)

```
Predict API error for fixture 1539007
Traceback (most recent call last):
  File ".../worldcup_predictor/api/routes/predictions.py", line 339, in predict_fixture
    result = pipeline.run(fixture_id=fixture_id)
  File ".../worldcup_predictor/orchestration/predict_pipeline.py", line 56, in run
    specialist_result = specialist.run(fixture_id=fixture_id)
  File ".../worldcup_predictor/agents/specialists/orchestrator.py", line 85, in run
    result = agent.run(fixture_id=int(fixture_id))
  File ".../worldcup_predictor/agents/specialists/expected_lineup_agent.py", line 67, in run
    payload, from_cache = get_or_build_expected_lineup(...)
  File ".../worldcup_predictor/lineups/expected_lineup_cache.py", line 86, in get_or_build_expected_lineup
    cache_expected_lineup(fixture_id, payload, kickoff_utc=kickoff_utc, settings=settings)
  File ".../worldcup_predictor/lineups/expected_lineup_cache.py", line 54, in cache_expected_lineup
    cache.set(CACHE_ENDPOINT, {"fixture_id": fixture_id}, payload, ttl_seconds=ttl)
  File ".../worldcup_predictor/cache/api_cache.py", line 67, in set
    self._path_for(key).write_text(...)
PermissionError: [Errno 13] Permission denied: '.cache/api_football/lineups/7c1712a8....json'
```

The API route masks all unhandled exceptions:

```351:360:worldcup_predictor/api/routes/predictions.py
    except Exception as exc:
        logger.exception("Predict API error for fixture %s", fixture_id)
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "fixture_id": fixture_id,
                "message": "Failed to run prediction pipeline.",
                "errors": [],
            },
        ) from exc
```

---

## Production Evidence

### Service identity

| Setting | Value |
|---------|-------|
| systemd `User` | `www-data` |
| systemd `Group` | `www-data` |
| `WorkingDirectory` | `/opt/worldcup-predictor` |

### Problem path ownership

```text
drwxr-xr-x  root:root     .cache/api_football/lineups/
-rw-r--r--  root:root     .cache/api_football/lineups/7c1712a8....json  (created 2026-06-20 10:47 UTC)
```

- `www-data` can **read** the file (`644`) but cannot **overwrite** it.
- The `lineups/` directory is `755 root:root` — `www-data` cannot create new files there either.

### Scale of pollution

```text
find /opt/worldcup-predictor/.cache -user root | wc -l  → 196 files
```

Additional root-owned write targets (non-fatal, logged as warnings):

```text
data/shadow/rule_a_live_validation.jsonl       root:root
data/validation/real_world_validation.jsonl    root:root
```

These caused `PermissionError` at 10:47:55 but predict still returned **200 OK** (fail-closed logging only).

### Timeline for fixture 1539007

| Time (UTC) | Event | Result |
|------------|-------|--------|
| 10:47:55 | `POST /api/predict/1539007` | **200 OK** (pipeline completed; shadow write warnings only) |
| 10:48:50 | `GET/POST /api/predict/1539007` | **200 OK** (likely served from prediction cache) |
| 10:49:07 | First `PermissionError` on `.cache/api_football/lineups/b0445f42....json` | Logged; other fixtures |
| 11:53:11 | Service restart — **6549c5e deployed** (Phase 27 + 28B) | — |
| 11:53:28 | `POST /api/predict/1539007` | **500** — lineup cache write blocked |
| 11:54:18 | Manual rollback `git reset --hard 1556fc0` + restart | — |
| 11:54:26 | `POST /api/predict/1539007` | **500** — same PermissionError |
| 11:55:29 | Second rollback restart (still `1556fc0`) | — |
| 11:55:39 | `POST /api/predict/1539007` | **500** — same PermissionError |
| 11:55:10+ | `GET /api/predict/1539007` | **404** — no valid cached prediction |

**Conclusion:** Failure correlates with **full pipeline re-run** (cache miss / invalidation), not with 28B Sportmonks code specifically. Rollback does not revert filesystem ownership.

### Current production git state (observed)

```text
HEAD → 1556fc0  (rollback already applied manually via SSH)
```

---

## Commit Comparison

| Commit | Date | Relevance |
|--------|------|-----------|
| **6fb9fec** | 2026-06-19 | Pre–Phase 22F. No `expected_lineup_agent` / lineup cache write path. Would avoid *this specific* crash but removes Phase 22–26 intelligence. |
| **1556fc0** | 2026-06-20 12:13 | Adds `expected_lineup_agent` + `expected_lineup_cache.py` (Phase 22F). Vulnerable when root pollutes `.cache`. **Currently on production.** |
| **6549c5e** | 2026-06-20 13:51 | Phase 27 + 28B. Adds prediction cache schema `27-v1` (invalidates stale caches → forces full pipeline). Adds Sportmonks split fetch + SQLite flag columns. **Not the PermissionError source.** |

### What changed in 6549c5e vs 1556fc0 (relevant to failure hypothesis)

| Area | Changed in 6549c5e? | Causes this 500? |
|------|---------------------|------------------|
| SQLite schema (Phase 42B columns) | Yes | **No** — no SQLite errors in logs |
| Sportmonks enrichment split | Yes | **No** — traceback is in lineup cache, not Sportmonks |
| Prediction cache policy (Phase 27) | Yes | **Indirect** — invalidates cached predictions → more full pipeline runs → exposes permission bug |
| `expected_lineup_cache.py` | **No** | — |
| `api_cache.py` | **No** | — |
| systemd service user | **No** | — |

### Ruled out

- SQLite migration / missing column errors — **none in journal**
- Sportmonks 403 / enrichment failure — **not in traceback**
- Phase 28B repository INSERT failures — **not observed**
- Authentication / nginx — predict reaches pipeline; fails inside Python

---

## Affected Files (failure chain)

| File | Role |
|------|------|
| `worldcup_predictor/agents/specialists/expected_lineup_agent.py` | Calls `get_or_build_expected_lineup()` during specialist orchestration |
| `worldcup_predictor/lineups/expected_lineup_cache.py` | Writes to `ApiCache` under `.cache/api_football/lineups/` |
| `worldcup_predictor/cache/api_cache.py` | `set()` → `Path.write_text()` — no PermissionError handling |
| `worldcup_predictor/api/routes/predictions.py` | Catches exception → generic 500 message |
| `deployment/systemd/worldcup-api.service` | Defines `User=www-data` |

---

## Why It Looked Like Phase 28B

1. Failure became **user-visible** immediately after deploying **6549c5e** (~11:53 UTC).
2. Phase 27 (bundled in same commit) **invalidates** prediction caches with `<22` agents or missing Phase 22 keys — forcing a **live full pipeline** instead of returning a cached prediction.
3. Before deploy, `POST /api/predict/1539007` often returned **200** from cache without rewriting lineup files.
4. Manual validation on the server as **root** (`python scripts/validate_phase28b_...`, curl tests) created root-owned artifacts in `.cache/api_football/lineups/` at **10:47 UTC** — primed the failure.

Phase 28B Sportmonks changes are a **red herring** for this incident.

---

## Is Rollback Required?

| Rollback target | Required? | Reason |
|-----------------|-----------|--------|
| **1556fc0** | **No** | Already applied; failure persists |
| **6fb9fec** | **No** | Would strip Phase 22–26 agents; does not fix root-owned cache files; wrong recovery |

**Rollback does not repair filesystem permissions.**

---

## Safest Recovery Path (awaiting approval)

### Immediate ops fix (recommended first)

Run on server as root — **not executed during this audit**:

```bash
# Restore ownership for API write paths
chown -R www-data:www-data /opt/worldcup-predictor/.cache
chown -R www-data:www-data /opt/worldcup-predictor/data/shadow
chown -R www-data:www-data /opt/worldcup-predictor/data/validation

# Verify
sudo -u www-data test -w /opt/worldcup-predictor/.cache/api_football/lineups && echo OK

# Restart API (if needed)
systemctl restart worldcup-api

# Re-test
curl -X POST "http://127.0.0.1:8000/api/predict/1539007"
```

Expected: **200 OK** on both `1556fc0` and `6549c5e` after ownership fix.

### Deploy strategy after recovery

1. Apply ownership fix while on `1556fc0` (confirm predict works).
2. Re-deploy **6549c5e** (Phase 27 + 28B) if still desired — no additional rollback needed.
3. Run validation scripts **as www-data**, not root:

   ```bash
   sudo -u www-data bash -lc 'cd /opt/worldcup-predictor && .venv/bin/python scripts/validate_phase28b_sportmonks_include_split.py'
   ```

### Process guardrails (prevent recurrence)

- Never run predict/validation scripts as `root` in `/opt/worldcup-predictor`.
- Add deploy post-step: `chown -R www-data:www-data .cache data/shadow data/validation`.
- Document in runbook: SSH troubleshooting should use `sudo -u www-data`.

---

## Fix Strategy (code — optional, post-recovery)

Low-risk hardening for a follow-up commit (not part of this audit):

1. **`api_cache.py`** — catch `PermissionError` on `set()`, log warning, continue (degraded cache).
2. **`expected_lineup_cache.py`** — wrap `cache_expected_lineup()` so agent completes even if cache write fails.
3. **Deploy script** — enforce `chown` after any root-invoked maintenance.

These are **defense in depth**; the primary fix is ownership correction.

---

## Validation Performed During Audit

| Check | Result |
|-------|--------|
| `journalctl -u worldcup-api -n 300` | PermissionError traceback captured |
| Production ownership inspection | `lineups/` + 196 cache files owned by root |
| Rollback verification (observed in SSH session) | `1556fc0` still returns 500 |
| Git diff `1556fc0..6549c5e` for lineup/cache | **No changes** |
| SQLite/schema errors in logs | **None found** |

---

## STOP

Audit complete. **No production modifications, deploys, or commits** were made.

Await approval before executing the ownership fix or re-deploying **6549c5e**.
