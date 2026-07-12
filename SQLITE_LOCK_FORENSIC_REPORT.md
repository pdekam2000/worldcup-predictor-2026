# SQLite Lock Forensic Report

Date: 2026-07-12

## Failure summary

| Field | Value |
|-------|-------|
| Unit | `worldcup-uefa-result-backfill-resume` |
| Started | 2026-07-11T20:59:11 UTC |
| Duration | ~31s |
| Exit | 1 |
| Error | `sqlite3.OperationalError: database is locked` |
| Log | `artifacts/result_backfill/uefa_resume_20260711_205911.log` |

## Answers

| # | Question | Finding |
|---|----------|---------|
| 1 | Code path | `init_database()` during repository/script startup |
| 2 | SQL operation | Schema DDL / migration writes at connection open |
| 3 | Provider inside transaction? | **No** — failure occurred **before** provider calls |
| 4 | Checkpoint in same transaction? | N/A — failed at startup |
| 5 | WAL enabled? | **No** (journal_mode=delete prior to hardening) |
| 6 | busy_timeout? | **Yes** — 30000 ms via `connect()` |
| 7 | Retry at init? | **No** (prior); **Yes** after hardening |
| 8 | Overlapping backfill units? | Possible — resume unit started while API/GPT Actions active |
| 9 | API/GPT long write transactions? | Concurrent prediction/odds writes during startup |
| 10 | Recoverable via resume? | **Yes** — subsequent `worldcup-uefa-result-backfill-api-restored` completed without lock |

## Classification

`VALIDATION_INCOMPLETE_DUE_TO_SSH_DISCONNECT` does **not** apply here — this was a genuine SQLite contention at DB open, not backfill logic failure.

## Hardening applied

- `PRAGMA journal_mode=WAL` on connect (when supported)
- `busy_timeout=30000` preserved
- Bounded `run_with_sqlite_retry` (5 attempts) on `init_database` and `save_snapshot`
- `single_instance_lock` for scheduled odds refresh overlap prevention

## Backfill baseline unchanged

FT without result = 12, targets done = 208, checkpoint batches = 79.
