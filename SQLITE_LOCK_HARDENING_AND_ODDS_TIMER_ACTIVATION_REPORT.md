# SQLite Lock Hardening and Odds Timer Activation Report

Date: 2026-07-12 (UTC)

## Final status

**SQLITE_LOCK_HARDENED_ODDS_TIMER_ACTIVE**

---

## 1. Acceptance report commit SHA

| Item | SHA |
|------|-----|
| `ACCEPTANCE_REPORT_COMMIT_SHA` | `75ebf44` |
| Message | `docs: finalize pre-kickoff fresh odds acceptance report` |

---

## 2. Root cause — `database is locked`

| Field | Value |
|-------|-------|
| Unit | `worldcup-uefa-result-backfill-resume` |
| When | 2026-07-11T20:59:11 UTC |
| Error | `sqlite3.OperationalError: database is locked` |
| Log | `artifacts/result_backfill/uefa_resume_20260711_205911.log` |

**Root cause:** Concurrent writers (`worldcup-api`, `worldcup-gpt-actions`) held the SQLite database while the backfill unit opened and ran `init_database()` DDL/migration writes. Journal mode was `delete` (not WAL). No bounded retry wrapped `init_database()`.

---

## 3. Failed SQL operation / path

- **Path:** `FootballIntelligenceRepository.__init__` → `init_database()` → schema DDL / `schema_meta` write
- **Operation:** `INSERT OR REPLACE INTO schema_meta` and related migration statements at startup
- **Provider call inside open write transaction?** **No** — failure occurred before any provider call

---

## 4. Previous WAL / busy_timeout state

| Setting | Before | After (production) |
|---------|--------|---------------------|
| `journal_mode` | `delete` | `wal` |
| `busy_timeout` | 30000 ms | 30000 ms |
| `init_database` retry | none | 5 attempts, exponential backoff |
| `save_snapshot` retry | none | 5 attempts |

Evidence: `artifacts/sqlite_lock/sqlite_runtime_baseline.json` (production capture 2026-07-12T02:23:40Z).

---

## 5. Concurrency changes applied

| Change | Location |
|--------|----------|
| WAL on connect | `worldcup_predictor/database/connection.py` |
| Schema guard (skip compat on empty DB) | `connection.connect()` |
| Bounded retry on `init_database` | `connection.init_database()` |
| Bounded retry on `save_snapshot` | `repository.FootballIntelligenceRepository` |
| `DEFAULT_MAX_ATTEMPTS = 5`, `max_delay = 4s` | `sqlite_retry.py` |
| Single-instance flock lock | `process_lock.py` |
| Backfill overlap refusal | `scripts/backfill_european_fixture_results.py` |
| Odds refresh overlap refusal | `scripts/run_scheduled_odds_refresh.py` |

**Provider/network pattern preserved:** `strict_live_refresh.refresh_fixture_odds_live` closes read connection in `finally` before opening a new repository for snapshot persistence.

---

## 6. Retry limits

- **Attempts:** 5 (lock errors only)
- **Backoff:** 0.5s base, cap 4s exponential
- **Not retried:** constraint violations, provider failures, invalid data

---

## 7. Lock regression results

| Validator | Result |
|-----------|--------|
| `scripts/validate_sqlite_lock_hardening.py` (local) | PASS |
| `scripts/validate_sqlite_lock_hardening.py` (production) | PASS |

Checks: WAL compatible, busy_timeout ≥ 15s, bounded retries, overlap rejected, no prediction/checkpoint mutation in test.

---

## 8. Overlap prevention

| Job | Lock name | Behavior |
|-----|-----------|----------|
| UEFA result backfill | `worldcup-uefa-result-backfill` | Second instance exits `skipped_overlap` |
| Scheduled odds refresh | `worldcup-odds-refresh` | Second oneshot exits `skipped_overlap` |

Lock directory: `/opt/worldcup-predictor/artifacts/locks` (production).

---

## 9. Odds refresh service

```ini
ExecStart=/opt/worldcup-predictor/.venv/bin/python scripts/run_scheduled_odds_refresh.py --max-api-calls 20
User=worldcup-gpt-actions
Type=oneshot
```

**Odds-only guarantees:** no prediction jobs, no WDE/ECSE/BTTS/O-U, no evaluations, owner-scope fixtures only, post-kickoff excluded, fresh fixtures skipped, quota guard active.

---

## 10. Timer

| Setting | Value |
|---------|-------|
| Unit | `worldcup-odds-refresh.timer` |
| Cadence | `OnCalendar=*:0/30` (every 30 minutes) |
| `Persistent` | `true` |
| `RandomizedDelaySec` | `120` |
| Enabled | **yes** (`systemctl enable --now`) |
| Next run (at enable) | 2026-07-12T02:31:24 UTC |

---

## 11. Per-run API cap and quota reserve

- **Cap:** 20 calls per run (`--max-api-calls 20`)
- **Quota guard:** `check_daily_live_budget()` before each refresh; stops on reserve breach
- **On-demand refresh-before-block:** unchanged (independent of timer)

---

## 12. Manual service smoke test (production)

| Metric | Value |
|--------|-------|
| Exit | success (oneshot deactivated) |
| `candidate_count` | 5 |
| `refreshed_count` | 5 |
| `provider_calls` | 5 (≤ 20) |
| `no_data_count` | 0 |
| `predictions_created` | 0 |
| `evaluations_created` | 0 |
| `quota_before.live_requests_today` | 0 |
| `quota_after.live_requests_today` | 5 |
| `status` | `ok` |
| Database lock | none observed |
| API key in logs | none |

---

## 13. WDE / ECSE / models

**Untouched.** No formula or model-path changes in this phase.

---

## 14. Post-deploy regression

| Check | Result |
|-------|--------|
| `worldcup-api` | active, `/api/health` → `{"status":"ok"}` |
| `worldcup-gpt-actions` | active |
| Bridge + refresh gate tests | **37/37 PASS** (production) |
| Pre-kickoff acceptance validator | **PASS** (1494204 / 1581037) |
| Odds timer validator | **25/25 checks PASS** |
| SQLite lock validator | **PASS** |

---

## 15. Result backfill baseline (unchanged)

```
FT_WITHOUT_RESULT = 12
TARGETS_DONE = 208
CHECKPOINT_BATCHES = 79
INTEGRITY = ok
DUPLICATE_FIXTURES = 0
ORPHAN_RESULTS = 0
```

No checkpoint reset, no retry of 12 provider-missing historical gaps.

---

## 16. Production source cleanliness

- Tracked source: aligned to `dde9679`
- Untracked: operational reports only (expected)
- No production-only patches applied

---

## 17. Final SHA alignment

| Stage | SHA |
|-------|-----|
| LOCAL HEAD | `dde9679` |
| ORIGIN/main | `dde9679` |
| PRODUCTION HEAD | `dde9679` |

### Commits in this phase

| SHA | Message |
|-----|---------|
| `75ebf44` | docs: finalize pre-kickoff fresh odds acceptance report |
| `4fb8e6b` | fix: harden SQLite concurrency for background provider jobs |
| `dde9679` | feat: add quota-safe scheduled odds refresh timer |

---

## 18. Rollback instructions

1. **Disable timer:** `systemctl disable --now worldcup-odds-refresh.timer`
2. **Remove units:** `rm /etc/systemd/system/worldcup-odds-refresh.{service,timer} && systemctl daemon-reload`
3. **Revert code:** `cd /opt/worldcup-predictor && git reset --hard 2a086cf` (pre-hardening) or `75ebf44` (docs only)
4. **Restart API services if needed:** `systemctl restart worldcup-api worldcup-gpt-actions`
5. **Verify backfill baseline** via `artifacts/provider_rescue/lightweight_validation.json`
6. **On-demand odds refresh** remains available regardless of timer state

---

## Artifacts

- `SQLITE_LOCK_FORENSIC_REPORT.md`
- `scripts/capture_sqlite_runtime_baseline.py`
- `artifacts/sqlite_lock/sqlite_runtime_baseline.json` (production runtime, not in git)
- `deployment/systemd/worldcup-odds-refresh.service`
- `deployment/systemd/worldcup-odds-refresh.timer`
- `scripts/validate_sqlite_lock_hardening.py`
- `scripts/validate_odds_refresh_timer.py`

---

**STOP** — Phase complete. No model feature integration started.
