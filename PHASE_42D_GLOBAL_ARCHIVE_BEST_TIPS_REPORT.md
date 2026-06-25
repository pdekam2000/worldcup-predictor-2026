# PHASE 42D — GLOBAL PUBLIC PREDICTION ARCHIVE + BEST TIPS PERFORMANCE CENTER

Generated: 2026-06-21

## Root cause

`/history` and `/api/user/prediction-history` only surfaced **PostgreSQL `user_prediction_history`** (per-user rows). Users with no personal predictions saw an empty history, even though the app had stored system/background predictions in **SQLite `worldcup_stored_predictions`** with evaluations in **`worldcup_prediction_evaluations`**.

## Data sources used

| Source | Purpose |
|--------|---------|
| PostgreSQL `user_prediction_history` | `scope=my` personal predictions |
| SQLite `worldcup_stored_predictions` | Global archive payloads |
| SQLite `worldcup_prediction_evaluations` | correct/wrong/pending status + market winrates |
| SQLite `fixtures` | match names / kickoff |
| Background daily payloads (`generated_by=background_daily`) | Tagged as `background_daily` source |

No prediction engine, WDE, or raw probability changes.

## Backend changes

### New modules

- `worldcup_predictor/api/global_prediction_archive.py` — list/merge/dedupe history by scope
- `worldcup_predictor/api/performance_center.py` — performance summary + Best Tips scoring
- `worldcup_predictor/api/routes/performance.py` — public performance routes

### Endpoints

| Endpoint | Behavior |
|----------|----------|
| `GET /api/history?scope=my\|global\|all` | Authenticated merged history (default frontend: `all`) |
| `GET /api/history/{entry_id}` | User UUID **or** `global-{fixture_id}` archive detail |
| `GET /api/performance/summary` | Evaluated winrates + market breakdown + reliability |
| `GET /api/best-tips` | Scored upcoming tips (no withheld/inconsistent/finished) |

Existing `/api/accuracy/summary` and `/api/user/prediction-history` preserved.

### Deduplication

`scope=all` merges by `fixture_id` — **user entry wins** over global archive entry.

### Global entry IDs

`global-{fixture_id}` (e.g. `global-12345`)

## Frontend changes

### History (`PredictionHistoryPage.jsx`)

- Tabs: **All Predictions** (default), **My Predictions**, **Global Archive**
- Source badges: Mine / System / Background
- Status colors: green correct, red wrong, yellow/gray pending
- Uses `fetchHistoryArchive({ scope })`

### Performance Center (`AccuracyCenter.jsx`)

- Renamed heading to **Performance Center**
- Uses `/api/performance/summary` + `/api/best-tips`
- Market rows show **sample size** + reliability badge (high/medium/low)
- Best Tips section with score, historical accuracy, confidence, reason
- Honest empty states (no fake production data; dev demo only in DEV)

## Winrate calculation

From SQLite evaluations (`worldcup_prediction_evaluations` + cached accuracy summary):

- `overall_accuracy = correct / evaluated`
- Per-market counts from evaluation status columns (`market_1x2_status`, `market_ou_status`, etc.)
- **Only finished/evaluated rows** contribute to accuracy numerators
- Pending counted separately, not as wrong

## Best Tips scoring

```
best_tip_score =
  0.45 * market_historical_accuracy
+ 0.30 * current_confidence (0–1)
+ 0.15 * sample_size_reliability (min(1, sample/50))
+ 0.10 * data_quality_score (fallback 0.7 if missing)
```

Excluded:

- Withheld / inconsistent markets (`consistency_status=withheld`, `display_allowed=false`)
- Finished matches
- Markets with sample size < 5

## Sample API payloads

### `GET /api/history?scope=all`

```json
{
  "status": "ok",
  "scope": "all",
  "history": [
    {
      "entry_id": "global-12345",
      "source": "background_daily",
      "fixture_id": 12345,
      "match_name": "Team A vs Team B",
      "result_status": "correct",
      "confidence": 72.5,
      "markets_count": 4,
      "can_open_detail": true
    }
  ],
  "stats": { "total": 1, "correct": 1, "wrong": 0, "pending": 0, "accuracy": 100.0 }
}
```

### `GET /api/performance/summary`

```json
{
  "status": "ok",
  "overall_accuracy": 0.74,
  "total_evaluated": 126,
  "correct_count": 93,
  "wrong_count": 33,
  "markets": [
    {
      "market_name": "1X2",
      "total": 126,
      "correct": 93,
      "wrong": 33,
      "accuracy": 0.7381,
      "sample_size": 126,
      "reliability_level": "high"
    }
  ],
  "disclaimer": "Calculated from finished matches only."
}
```

## Validation

```bash
python scripts/validate_phase42d_global_archive_best_tips.py
```

**Result: 37/37 PASS**

Covers: scope my/global/all, merge dedupe, global detail builder, performance/best-tips endpoints, no engine changes, auth required for history, no private user leakage in global rows.

## Production deploy

**Deployed:** 2026-06-21 UTC

| Step | Result |
|------|--------|
| Full backup (SQLite + frontend dist + env) | OK |
| Backend tarball extract | OK |
| Frontend dist deploy | OK |
| `systemctl restart worldcup-api` | active |
| `systemctl reload nginx` | active |
| Local validation on server | 33/37 PASS (4 frontend *source* checks fail — no `base44-d/src` on prod; expected) |
| Runtime smoke tests | **SMOKE_ALL_PASS** |

**Backup path:** `/opt/worldcup-predictor/backups/deploy-phase42d-20260621-124510`

**Pre-deploy commit:** `267812e6e1c71258b78373161ade915c00b3ed71`

### Production smoke results

| Check | Result |
|-------|--------|
| `/api/health` | 200 |
| `/history` page | 200 |
| `/api/accuracy/summary` | 200 (unchanged) |
| `/api/performance/summary` | 200 — 2 evaluated, real metrics |
| `/api/best-tips` | 200 — empty tips (no upcoming fixtures; honest) |
| `/api/history?scope=all` | 401 without auth |
| `/api/history?scope=global` | 401 without auth |
| Login endpoint | 401 on bad creds |
| Predict endpoint | 404 (unchanged, not 500) |
| Frontend bundle | global archive + performance center strings present |

### Live production sample (`GET /api/performance/summary`)

```json
{
  "status": "ok",
  "overall_accuracy": 1.0,
  "total_evaluated": 2,
  "correct_count": 2,
  "wrong_count": 0,
  "pending_count": 0,
  "markets": [
    {
      "market_name": "1X2",
      "total": 2,
      "correct": 2,
      "wrong": 0,
      "accuracy": 1.0,
      "sample_size": 2,
      "reliability_level": "low"
    }
  ],
  "disclaimer": "Calculated from finished matches only."
}
```

Global archive fixture IDs present in SQLite: `1539007`, `1489393`, `1489392` (detail via `GET /api/history/global-{fixture_id}` when authenticated).

### Rollback plan

1. `systemctl stop worldcup-api`
2. Restore from `/opt/worldcup-predictor/backups/deploy-phase42d-20260621-124510/`:
   - `football_intelligence.db` → `data/`
   - `frontend_dist/` → `/var/www/worldcup/frontend/dist/`
   - `repo_snapshot_pre.tar.gz` → prior backend files
3. `systemctl start worldcup-api && systemctl reload nginx`

## Final status

```
PHASE_42D_STATUS = PRODUCTION_ACTIVE
```
