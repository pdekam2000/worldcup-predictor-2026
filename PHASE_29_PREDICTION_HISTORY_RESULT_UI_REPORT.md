# Phase 29 — Prediction History Result UI

**Status:** Implementation complete — validation passed locally. **Not deployed** (awaiting approval).

## Summary

Phase 29 adds live match-result evaluation to user prediction history and upgrades the `/history` UI with correctness badges, score display, and filters — without changing WDE, calibration, promotion modes, Match Center, or Prediction Detail.

---

## Files Changed

| File | Change |
|------|--------|
| `worldcup_predictor/api/prediction_history_evaluation.py` | **New** — fixture outcome resolver + result classification |
| `worldcup_predictor/api/routes/user.py` | Enriched `/prediction-history`; added `/prediction-history/results`; dashboard uses evaluated stats |
| `base44-d/src/api/saasApi.js` | `resultFilter` query param; `fetchPredictionHistoryResults()` |
| `base44-d/src/pages/PredictionHistoryPage.jsx` | Card UI, color badges, filters, empty/error/retry states |
| `scripts/validate_phase29_prediction_history_results.py` | **New** — classification + mapping validation |

**Unchanged:** WDE, calibration, promotion adapters, Match Center, Prediction Detail routes, PostgreSQL schema.

---

## API Endpoints

### Extended: `GET /api/user/prediction-history`

Query params:

| Param | Default | Values |
|-------|---------|--------|
| `limit` | 50 | 1–100 |
| `offset` | 0 | ≥ 0 |
| `result_filter` | `all` | `all`, `correct`, `wrong`, `pending` |

### Alias: `GET /api/user/prediction-history/results`

Same payload as above (explicit Phase 29 endpoint).

### Response item fields

| Field | Description |
|-------|-------------|
| `fixture_id` | API-Football fixture ID |
| `match_date` | Scheduled kickoff (ISO) |
| `home_team` / `away_team` | Team names |
| `predicted_1x2` | `home` / `draw` / `away` |
| `predicted_confidence` | 0–100 float |
| `actual_result` | `home_win` / `draw` / `away_win` / null |
| `final_score` | e.g. `2-1` |
| `is_finished` | bool |
| `is_correct` | `true` / `false` / `null` |
| `evaluated_at` | ISO timestamp when result was known |
| `result_status` | `correct` / `wrong` / `pending` / `unknown` |
| `data_quality` | From prediction cache if available |
| `agent_count` | Specialist agent count from cache |
| `cache_schema_version` | e.g. `27-v1` |

**Backward compatibility:** legacy fields retained — `prediction_1x2`, `confidence`, `result` (`correct`/`incorrect`/`pending`), `viewed_at`, `id`, `league`.

### Stats block

```json
{
  "total": 12,
  "correct": 5,
  "wrong": 3,
  "pending": 4,
  "unknown": 0,
  "accuracy": 62.5
}
```

---

## Classification Logic

Evaluation order for each `fixture_id`:

1. `data/results/match_results.jsonl` (`MatchResultsStore`)
2. SQLite `fixture_results` + `fixtures.status`
3. If status ∈ `{FT, AET, PEN}` but no score → `result_status = unknown`

| Condition | `result_status` | `is_correct` |
|-----------|-----------------|--------------|
| Match not finished | `pending` | `null` |
| Finished, pick matches actual | `correct` | `true` |
| Finished, pick wrong | `wrong` | `false` |
| Finished, score unavailable | `unknown` | `null` |

**Pick mapping:**

- Predicted `home` ↔ actual `home_win`
- Predicted `draw` ↔ actual `draw`
- Predicted `away` ↔ actual `away_win`

Uses existing `actual_result()` from `schedule/match_center.py`.

---

## Frontend

**Route:** `/history` (existing — enhanced, not replaced)

**UI:**

- Summary cards: Total, Correct, Wrong, Accuracy
- Filter tabs: All / Correct / Wrong / Pending
- Per-match cards with green (correct), red (wrong), yellow (pending), neutral (unknown) badges
- Shows teams, date, prediction (1/X/2), confidence, actual result, final score
- Links to `/prediction/:fixture_id`
- Empty state when no rows
- Error banner + Retry on API failure
- Refresh button

Match Center and Prediction Detail untouched.

---

## Validation

```text
python scripts/validate_phase29_prediction_history_results.py
→ All 16 Phase 29 checks passed
```

Covers:

- `pending`, `correct`, `wrong`, `unknown` classification
- Required API payload fields
- Legacy `result` field mapping
- Filter helpers
- Frontend-safe handling of missing optional fields

---

## Deployment Steps (after approval)

1. Deploy backend + frontend build to production
2. Ensure `www-data` owns writable paths (see Phase 28B ops note)
3. Confirm PostgreSQL `user_prediction_history` has rows (created on authenticated `POST /api/predict/{id}`)
4. Smoke test:
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     "http://127.0.0.1:8000/api/user/prediction-history?result_filter=all"
   ```
5. Open `/history` in browser — verify badges and filters
6. No Alembic migration required (evaluation is computed at read time)

---

## Notes

- History rows remain `PENDING` in PostgreSQL; evaluation is **computed on read** from fixture results — no schema migration needed.
- Finished matches without ingested results show `unknown` until results store/SQLite is populated.
- Dashboard `recent_predictions` now includes the same evaluated fields for consistency.

**STOP — awaiting approval before deploy.**
