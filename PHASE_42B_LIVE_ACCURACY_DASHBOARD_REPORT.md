# PHASE 42B — Live Accuracy Dashboard Report

**Date:** 2026-06-21  
**Mode:** Implement → Validate → Report  
**Deploy status:** **Not deployed** — awaiting approval

---

## Executive summary

The React `/accuracy` page now loads **live platform accuracy** from `GET /api/accuracy/summary` instead of hardcoded mock charts. Data comes from the existing World Cup SQLite evaluation pipeline (`worldcup_accuracy_summary` / `worldcup_prediction_evaluations`), with JSONL learning-memory fallback when SQLite has no evaluated rows. Production returns a real empty/zero state when no evaluations exist — no fake accuracy. Local validation: **35/35 PASS**.

---

## Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/api/public_accuracy_summary.py` | **New** — SaaS-safe platform summary builder |
| `worldcup_predictor/api/routes/accuracy.py` | **New** — `GET /accuracy/summary` |
| `worldcup_predictor/api/main.py` | Register `accuracy_router` |
| `base44-d/src/pages/AccuracyCenter.jsx` | Replaced mock UI with live API + empty/loading/error states |
| `base44-d/src/lib/accuracyDemoData.js` | **New** — dev-only demo fallback (labeled) |
| `base44-d/src/api/saasApi.js` | Added `fetchAccuracySummary()` |
| `scripts/validate_phase42b_live_accuracy_dashboard.py` | **New** validation suite |

**Not changed:** prediction engine, WDE, Stripe/billing, auth, `/admin/accuracy`, `/history` logic, database migrations.

---

## Backend endpoint

### `GET /api/accuracy/summary`

- **Auth:** None (public aggregate platform stats)
- **Query:** `competition` (default `world_cup_2026`)

**Response fields:**

| Field | Description |
|-------|-------------|
| `overall_accuracy` | Win rate on evaluated predictions (0–1 or null) |
| `total_predictions` | Stored prediction count |
| `correct_predictions` / `wrong_predictions` / `pending_predictions` | Counts |
| `accuracy_by_market` | Array: 1X2, O/U 2.5, BTTS, Double Chance (+ First Goal Team from JSONL fallback) |
| `recent_results` | Recent evaluated rows (fixture, market, prediction, actual, status, confidence) |
| `updated_at` | ISO timestamp |
| `data_source` | `worldcup_sqlite_evaluations` \| `jsonl_learning_memory` \| `empty` |
| `disclaimer` | Finished matches only |

**Data source priority:**

1. SQLite `worldcup_accuracy_summary` + evaluation rows (same pipeline as admin)
2. JSONL `reports/accuracy/accuracy_summary.json` via `AccuracyTrackerService`
3. Empty/zero state (`data_source: "empty"`) — **no fabricated accuracy**

Admin routes unchanged; no admin internals exposed.

---

## Frontend changes

**`/accuracy` (AccuracyCenter.jsx):**

- Fetches `fetchAccuracySummary()` on load + Refresh button
- Cards: Overall Accuracy, Correct, Wrong, Pending
- **Accuracy by Market** bar chart + table
- **Recent Evaluated Predictions** table (green/red/yellow status badges)
- Copy: *"Accuracy is calculated from finished matches only."*
- Empty state: *"No completed prediction evaluations yet."*
- Link to `/history` for personal history
- **Dev only:** if API returns empty, shows `accuracyDemoData.js` with yellow *"Demo data"* banner
- Production build never uses demo fallback on error (shows error message instead)

**Removed:** hardcoded `monthlyData`, `leagueData`, `pieData`, `recentResults` mock arrays.

---

## Data source used (local validation)

Local run returned `data_source: "worldcup_sqlite_evaluations"` with 2 evaluated fixtures in SQLite.

---

## Sample API response (truncated)

```json
{
  "status": "ok",
  "overall_accuracy": 1.0,
  "total_predictions": 2,
  "correct_predictions": 2,
  "wrong_predictions": 0,
  "pending_predictions": 0,
  "accuracy_by_market": [
    {
      "market": "1X2",
      "total": 2,
      "correct": 2,
      "wrong": 0,
      "pending": 0,
      "accuracy": 1.0
    },
    {
      "market": "Over/Under 2.5",
      "total": 2,
      "correct": 2,
      "wrong": 0,
      "pending": 0,
      "accuracy": 1.0
    }
  ],
  "recent_results": [
    {
      "fixture_id": 12345,
      "match_name": "Team A vs Team B",
      "market": "1X2",
      "prediction": "home",
      "actual_result": "home_win",
      "final_score": "2-1",
      "status": "correct",
      "confidence": 72.0,
      "match_date": "2026-06-15T18:00:00"
    }
  ],
  "updated_at": "2026-06-21T12:00:00",
  "data_source": "worldcup_sqlite_evaluations",
  "competition_key": "world_cup_2026",
  "disclaimer": "Accuracy is calculated from finished matches only."
}
```

When no evaluations exist, `overall_accuracy` is `null`, counts are `0`, `recent_results` is `[]`, and `data_source` is `"empty"`.

---

## Validation results

```
Phase 42B validation: 35/35 PASS
```

| Check | Result |
|-------|--------|
| `GET /api/accuracy/summary` 200 | PASS |
| No fake/mock data source in API | PASS |
| Empty state | PASS |
| Overall + market accuracy math | PASS |
| Frontend no hardcoded mock arrays | PASS |
| `/api/admin/accuracy` still 401 unauth | PASS |
| `/api/user/prediction-history` still works | PASS |
| Prediction engine / WDE untouched | PASS |

**Run locally:**

```bash
python scripts/validate_phase42b_live_accuracy_dashboard.py
```

---

## UI notes

- **Green** badges/bars: correct predictions
- **Red:** wrong
- **Yellow/gray:** pending
- Empty state shows chart icon + CTA to personal `/history`
- Dev demo banner is yellow and explicit (not shown in production builds when data exists)

Screenshots not captured in this environment; verify visually after deploy at `/accuracy`.

---

## Deploy steps (after approval)

1. Backup production (same pattern as Phase 41D):
   ```bash
   BACKUP=/opt/worldcup-predictor/backups/deploy-phase42b-$(date -u +%Y%m%d-%H%M%S)
   mkdir -p "$BACKUP"
   pg_dump "$DATABASE_URL" -Fc -f "$BACKUP/postgres.dump"  # optional
   cp -a /var/www/worldcup/frontend/dist "$BACKUP/frontend_dist"
   ```

2. Deploy backend files + rebuild frontend (`npm run build` in `base44-d`).

3. Restart API:
   ```bash
   sudo systemctl restart worldcup-api
   ```

4. Validate on server:
   ```bash
   curl -sS https://footballpredictor.it.com/api/accuracy/summary | head -c 500
   python scripts/validate_phase42b_live_accuracy_dashboard.py
   ```

5. Smoke: open `/accuracy` — confirm live data or honest empty state (no 73% mock).

---

## Rollback plan

```bash
BACKUP=/opt/worldcup-predictor/backups/deploy-phase42b-<timestamp>
APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist

rm -f "$APP/worldcup_predictor/api/public_accuracy_summary.py"
rm -f "$APP/worldcup_predictor/api/routes/accuracy.py"
# Restore main.py from backup or remove accuracy_router lines
cp -a "$BACKUP/frontend_dist/." "$FRONTEND/"

systemctl restart worldcup-api
```

No database migration was added — rollback is code-only.

---

**Phase 42B complete. STOP — awaiting deploy approval.**
