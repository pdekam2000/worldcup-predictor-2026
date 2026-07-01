# PHASE DAILY-OWNER-1 — Daily Owner Prediction Cycle Report

## Summary

Owner-only daily workflow implemented: fixture discovery → data completeness → cache-first provider fetch → WDE/ECSE generation (no logic changes) → result sync/evaluation → markdown + JSON reports. No public exposure, no WDE/ECSE/EGIE/billing changes.

**Final recommendation: `NEED_ODDS_IMPORT`**

Today's sample fixture (Netherlands vs Morocco, WC 2026) has ECSE snapshot coverage but lacks fresh 1X2/O/U/BTTS odds in `odds_snapshots`. Run with provider calls enabled (not `--no-provider-calls`) or import odds via existing EURO-C path before relying on daily STRONG_SIGNAL labels.

---

## Files changed / created

| Path | Role |
|------|------|
| `worldcup_predictor/owner_daily/__init__.py` | Package entry |
| `worldcup_predictor/owner_daily/constants.py` | Competitions, paths, owner labels |
| `worldcup_predictor/owner_daily/provider_call_log.py` | Quota guard + `logs/daily_provider_calls_YYYYMMDD.jsonl` |
| `worldcup_predictor/owner_daily/fixture_discovery.py` | Part A — DB-first discovery + provider backfill |
| `worldcup_predictor/owner_daily/data_completeness.py` | Part B — per-fixture missing-field audit |
| `worldcup_predictor/owner_daily/provider_fetch.py` | Part C/D — priority fetch, cache-first, fallback |
| `worldcup_predictor/owner_daily/predictions.py` | Part E — WDE/ECSE via existing pipelines |
| `worldcup_predictor/owner_daily/report.py` | Part F — markdown + JSON owner report |
| `worldcup_predictor/owner_daily/result_sync.py` | Part G — ECSE result sync + WDE/ECSE evaluation |
| `worldcup_predictor/owner_daily/cycle.py` | Full orchestrator |
| `scripts/owner_daily_predictions.py` | Main CLI |
| `scripts/run_daily_owner_prediction_cycle.py` | Scheduler entry + cron/systemd examples |
| `scripts/validate_daily_owner_prediction_cycle.py` | Part J validation |
| `DAILY_OWNER_PREDICTION_CYCLE_REPORT.md` | This report |

---

## Workflow steps

1. **Pre result sync** — `sync_ecse_snapshot_results` per supported competition; provider-backed FT/AET/PEN only.
2. **Fixture discovery** — Resolve date in `Europe/Vienna`; query local `fixtures`; optional API-Football / Sportmonks / OddAlerts probe; dedupe by teams+kickoff.
3. **Data completeness** — Audit fixture basics, odds markets, intelligence, WDE/ECSE/shadow/evaluation fields with priority + provider candidate.
4. **Provider fetch** — Cache-first; caps per provider; force refresh on stale/live/pre-match window; odds fallback API-Football → OddAlerts.
5. **Predictions** — `PredictPipeline` (WDE) and `build_ecse_live_prediction` (ECSE); `generated_by=owner_daily_predictions`; skip unless `--force`.
6. **Post result sync + evaluation** — WDE `run_evaluate_worldcup_results`; ECSE `run_ecse_evaluations`.
7. **Reports** — `reports/owner/daily_predictions_YYYYMMDD.{md,json}`; `artifacts/daily_data_completeness_YYYYMMDD.json`; provider call log append.

---

## Providers used

| Provider | Use |
|----------|-----|
| **API-Football** | Fixtures by date, status refresh, odds (primary), injuries/lineups path reserved |
| **Sportmonks** | Supplementary UEFA/WC fixtures; xG/pressure enrichment when configured |
| **OddAlerts** | Odds fallback; fixture support probe |

All calls logged to `logs/daily_provider_calls_YYYYMMDD.jsonl` with cache_hit, quota_counter, request_reason.

---

## Quota guards

CLI flags (defaults):

- `--max-api-football-calls 100`
- `--max-sportmonks-calls 100`
- `--max-oddalerts-calls 100`
- `--only-missing` (default true)
- `--dry-run`, `--force-refresh`, `--no-provider-calls`

`ProviderQuotaGuard` blocks live calls when caps exceeded; cache hits do not increment counters.

---

## Data completeness fields

Checked per fixture: fixture_id, provider IDs, competition_key, season, kickoff, teams, status; odds (1X2, O/U 1.5/2.5/3.5, BTTS, DC, correct score, bookmaker count, timestamp, source); form, standings, H2H, injuries, lineups, formations, referee, team stats, xG, pressure, events; WDE/ECSE/shadow/evaluation presence; stale status after kickoff.

---

## Daily report paths

- Markdown: `reports/owner/daily_predictions_20260630.md`
- JSON: `reports/owner/daily_predictions_20260630.json`
- Completeness: `artifacts/daily_data_completeness_20260630.json`
- Cycle summary: `artifacts/daily_owner_cycle_20260630.json`
- Validation: `artifacts/daily_owner_prediction_cycle_validation.json`
- Provider log: `logs/daily_provider_calls_20260630.jsonl` (appended on runs with provider activity)

---

## Validation result

```
python scripts/validate_daily_owner_prediction_cycle.py
```

**18 / 18 checks passed** (see `artifacts/daily_owner_prediction_cycle_validation.json`).

Verified: today fixtures discovered; quota caps; reports created; WDE/ECSE skip/generate traces; provider-backed odds sample; no daily-discovery duplicates; no duplicate owner predictions; public predictions untouched; WDE/ECSE/EGIE/billing unchanged; result sync competitions supported.

---

## Sample run output

```bash
python scripts/owner_daily_predictions.py --date today --timezone Europe/Vienna --limit 20 --dry-run --no-provider-calls
```

- **Date:** 2026-06-30 (Europe/Vienna)
- **Fixtures:** 1 — Netherlands vs Morocco (`world_cup_2026`, kickoff 03:00 CEST)
- **WDE:** dry-run would generate (existing production prediction preserved)
- **ECSE:** skipped — `missing_odds` (no fresh odds snapshot for lambda inputs)
- **Owner label:** `DATA_MISSING` (WDE load from public store not stamped `owner_daily_predictions`)

Report excerpt:

| Fixture | ECSE Top-1 | ECSE Top-3 | Label |
|---------|------------|------------|-------|
| Netherlands vs Morocco | 1-0 | 1-0, 1-1, 2-0 | DATA_MISSING |

Owner note in report: *"Use Top-3 exact-score cover, not single-score confidence. ECSE exact-score Top-1 is naturally low probability."*

---

## Remaining missing data (2026-06-30 sample)

From `artifacts/daily_data_completeness_20260630.json`:

- **High priority:** `odds_1x2`, `odds_ou_2_5`, `odds_btts`, `wde_prediction`
- **Medium:** form, standings, H2H, injuries, lineups, referee, team statistics
- **Low / optional:** xG, pressure_index, events, owner_shadow_lab

**Action:** Run without `--no-provider-calls` during a live API window, or pre-seed odds via `import_uefa_odds` / WC odds import before the morning cycle.

---

## Scheduler (not installed)

```bash
python scripts/run_daily_owner_prediction_cycle.py --show-schedule-examples
```

Documents cron at 08:00 Vienna, 2-hour pre-kickoff refresh, 23:00 result sync, and systemd timer examples. No cron/systemd units were installed.

---

## CLI reference

```bash
# Full daily cycle
python scripts/owner_daily_predictions.py --date today --timezone Europe/Vienna --limit 20

# Specific date + competitions
python scripts/owner_daily_predictions.py --date 2026-06-30 --timezone Europe/Vienna \
  --competitions world_cup_2026 champions_league europa_league conference_league --limit 20

# Scheduler wrapper
python scripts/run_daily_owner_prediction_cycle.py --timezone Europe/Vienna
```

---

## Final recommendation

### `NEED_ODDS_IMPORT`

The daily cycle infrastructure is ready (`DAILY_OWNER_CYCLE_READY` after odds import). For production daily use:

1. Enable provider calls (remove `--no-provider-calls` for scheduled runs).
2. Import or refresh 1X2 + O/U 2.5 + BTTS odds for today's fixtures.
3. Re-run `python scripts/owner_daily_predictions.py --date today --timezone Europe/Vienna`.
4. Re-validate; expect recommendation to move to `DAILY_OWNER_CYCLE_READY` when ECSE lambda inputs and WDE paths are satisfied.

No public routes, prediction scoring logic, EGIE, or billing were modified.
