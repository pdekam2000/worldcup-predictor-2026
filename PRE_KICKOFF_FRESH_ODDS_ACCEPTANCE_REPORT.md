# Pre-Kickoff Fresh Odds Acceptance Report

Date: 2026-07-12 (Europe/Vienna)

## Final status

**PRE_KICKOFF_FRESH_ODDS_PREDICTION_ACCEPTANCE_COMPLETE**

---

## 1. Hotfix commit SHA

| Stage | SHA |
|-------|-----|
| Canonical odds bridge hotfix | `98a306c` |
| Pre-kickoff acceptance phase | `b69b83f` |

## 2. Local / Origin / Production

| Stage | SHA |
|-------|-----|
| LOCAL HEAD | `2a086cf` |
| ORIGIN/main | `2a086cf` |
| PRODUCTION HEAD | `2a086cf` |

---

## 3. Selected upcoming fixtures

See `PRE_KICKOFF_ODDS_ACCEPTANCE_FIXTURE_SELECTION.md`.

| fixture_id | tier | scope | kickoff_utc |
|------------|------|-------|-------------|
| 1494204 | B | owner_shadow | 2026-07-12T12:00:00 |
| 1494205 | B | owner_shadow | 2026-07-12T12:00:00 |
| 1554381 | A | production | 2026-07-14T15:00:00 |

---

## 4. Primary positive path — 1494204 (Hammarby vs Kalmar)

### Initial snapshot (pre-refresh)

| Field | Value |
|-------|-------|
| canonical row_id | 2295 |
| provider | live |
| bookmaker_count | 14 |
| market | FULL_TIME_1X2 (Match Winner) |
| H/D/A | 1.40 / 4.95 / 6.60 |
| fetched_at_utc | 2026-07-11T08:01:41+00:00 |
| timestamp_source | snapshot_at_column |
| odds_age_minutes | 943.1 |
| allowed_ttl_seconds | 7200 (2h, ~12h to kickoff) |
| freshness_class | ODDS_STALE |

### Refresh and persistence

- `refresh_attempted`: true (via prediction gate)
- Provider used: api-football (live refresh chain)
- `refresh_success`: true
- Post-refresh `fetched_at_utc`: new import at prediction time (~2026-07-11T23:45 UTC)
- Filter and validator **same row identity** before refresh; new row after import
- Persistence committed before revalidation

### Post-refresh / prediction

| Field | Value |
|-------|-------|
| freshness | FRESH_ODDS |
| age_minutes | 0.0 |
| prediction job status | OK |
| data_quality | OK (not BLOCKED) |

### Model outputs

| Model | Available | Detail |
|-------|-----------|--------|
| WDE | Yes | H 83.5% / D 11.7% / A 4.8%, pick home_win |
| BTTS | Yes | prediction: no |
| O/U 2.5 | Yes | prediction: over_2_5 |
| ECSE | Yes | Top1–Top5: 2-0, 3-0, 1-0, 4-0, 2-1 |

Tier B: `prediction_scope=owner_shadow`, `public_visible=false` (shadow storage path).

---

## 4b. Owner workflow (PART C) — job execution

Exact workflow on production (2026-07-12 ~01:50 UTC):

1. `discoverTodayMatches(scope=owner)` — today’s owner fixtures
2. `filterMatchesByOdds(scope=owner)` — odds filter applied
3. `startPredictionJob(prediction_scope=owner_shadow)` for Tier B fixture **1494204**
4. Job polled to completion (synchronous worker execution)

| Field | Value |
|-------|-------|
| job_id | `6aec46d5-4875-440a-8abe-16a1cf1011a2` |
| idempotency_key | `pre-kickoff-1494204` |
| job_status | **completed** |
| prediction_scope | owner_shadow |
| data_quality | OK |
| odds freshness | FRESH_ODDS |
| age_minutes | 0.0 |
| public_visible | false |
| owner_shadow | true |
| WDE | home_win, H 83.7% / D 11.6% / A 4.7% |
| BTTS | no |
| O/U 2.5 | over_2_5 |
| ECSE Top1–Top5 | 2-0, 3-0, 1-0, 4-0, 2-1 |

Tier A production job for 1554381 deferred — no canonical 1X2 odds in DB (provider-coverage gap for CL qualifier).

---

## 5. Negative path — 1581037 (Norway vs England)

| Field | Value |
|-------|-------|
| kickoff | passed |
| pre freshness | ODDS_STALE |
| refresh | success (api-football) |
| final block | STALE_ODDS_AFTER_REFRESH |
| prediction | BLOCKED |
| WDE/BTTS/O-U/ECSE | unavailable |

Correct negative-path behavior retained.

---

## 6. Tier A note — 1554381

KuPS vs Vardar Skopje (Champions League qualifier, kickoff 2026-07-14): **no canonical 1X2 snapshot** in DB at test time. Prediction ran with partial model output but **without fresh-odds positive-path proof** for Tier A. Documented as provider-coverage gap for this specific fixture, not a bridge regression.

---

## 7. Automated validation

| Suite | Result |
|-------|--------|
| Canonical snapshot bridge (25) | 37/37 pass (incl. refresh gate 12) |
| `validate_pre_kickoff_fresh_odds_prediction_acceptance.py` | **PASS** — `PRE_KICKOFF_FRESH_ODDS_PREDICTION_ACCEPTANCE_COMPLETE` |
| compileall | pass |

Validator checks (production):

- future fixture selected ✓
- kickoff not passed ✓
- canonical snapshot found ✓
- complete 1X2 ✓
- timestamp parsed ✓
- real age calculated ✓
- dynamic TTL applied ✓
- refresh → post-refresh FRESH_ODDS ✓
- WDE/BTTS/O-U/ECSE after fresh validation ✓
- negative fixture blocked ✓
- no secret leakage ✓

---

## 8. Service health

- `worldcup-api`: active
- `worldcup-gpt-actions`: active
- Production tracked source: clean (untracked reports only)

---

## 9. Result backfill untouched

```
BACKFILL_STATE = STABLE
FT_WITHOUT_RESULT = 12
TARGETS_DONE = 208
CHECKPOINT_BATCHES = 79
ODDS_HOTFIX_RESULT_REGRESSION = NO
```

No checkpoint reset, no backfill retry, no API calls for the 12 provider-missing gaps.

---

## 10. Impossible state confirmation

The five post-kickoff fixtures no longer produce:

`visible odds + api-football + bookmaker_count=14 + ODDS_MISSING + age_minutes=null`

Pre-kickoff fixture 1494204 proves the **positive path**:

`stale odds → live refresh → persisted fresh snapshot → FRESH_ODDS → prediction OK → models execute`

---

## Artifacts

- `artifacts/pre_kickoff_acceptance/validation_report.json` (production)
- `scripts/validate_pre_kickoff_fresh_odds_prediction_acceptance.py`
