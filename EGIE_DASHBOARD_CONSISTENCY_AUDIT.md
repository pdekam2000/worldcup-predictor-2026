# EGIE Dashboard Consistency Audit

**Mode:** Read-only audit — no code changes, no deploy  
**Date:** 2026-06-22  
**Question:** Why does Phase B report **Published = 48, NO_PICK = 2**, while the Phase 51G dashboard shows **Published = 49, NO_PICK = 19** (and **25** at audit time)?

---

## Executive verdict

| Metric | Phase B (snapshot) | Dashboard headline | Truth at audit (production DB) |
|--------|-------------------|-------------------|--------------------------------|
| **Published** | 48 | 49 | **49 rows** / **49 distinct fixtures** |
| **NO_PICK** | 2 | 19 → 25 | **25 rows** / **3 distinct fixtures** (2 upcoming + 1 historical) |

**The numbers measure different things.**

- **Phase B** counted **unique upcoming Premier League fixtures** in the first Phase B picks batch (2026/27 season): 48 published + 2 NO_PICK = **50 fixtures**.
- **Dashboard** counts **all PostgreSQL rows** in `goal_timing_predictions` with **no season, batch, or deduplication filter** — and **repeated `/picks` / predict runs append new rows** (no upsert per fixture).

**Upcoming-only distinct counts still match Phase B exactly:** 48 published + 2 NO_PICK.

The dashboard is **internally consistent** (API = DB = UI formula). It is **not comparable** to Phase B without applying the same scope (upcoming batch, distinct fixtures).

---

## 1. Source of Published Picks count

### Dashboard / API

`GoalTimingDashboardService` → `GoalTimingRepository.prediction_monitoring_counts()`:

```sql
SELECT COUNT(*) FROM goal_timing_predictions WHERE no_prediction_flag = false
```

- **Table:** PostgreSQL `goal_timing_predictions`
- **Filter:** `no_prediction_flag = false` only
- **Scope:** **All time**, all leagues in table (currently **only `premier_league`**)
- **No filter on:** season, `match_date`, `status`, batch, or “latest row per fixture”

### Phase B

Documented in `EGIE_EVALUATION_PIPELINE_AUDIT.md` and production Phase B run:

- **380 upcoming** PL fixtures synced to SQLite (2026/27 season)
- **First picks generation** over that upcoming set
- **48** fixtures passed DQ → published (`no_prediction_flag = false`)
- **2** fixtures failed DQ (thin history, e.g. Ipswich / Sunderland, DQ ≈ 0.4286) → NO_PICK

Phase B = **point-in-time, upcoming-season, per-fixture outcome** — not a cumulative row count.

---

## 2. Source of NO_PICK count

### Dashboard / API

```sql
SELECT COUNT(*) FROM goal_timing_predictions WHERE no_prediction_flag = true
```

Same table, **all-time row count**, no deduplication.

UI “reasons” list: `list_no_pick_predictions(limit=20)` — shows up to **20 rows**, not all 25.

### Phase B

**2 upcoming fixtures** where the engine set `no_prediction_flag = true` on first pass (DQ below 0.45).

### Why 19 (51G deploy) → 25 (audit now)?

Each call to `/api/goal-timing/picks` can **insert another row** for fixtures whose latest stored row is NO_PICK (`save_prediction` is INSERT-only; `get_prediction_by_fixture` returns latest, but a new NO_PICK row is still appended on re-run).

Production duplicate pattern (audit):

| `fixture_id` | Total rows | NO_PICK rows | Published rows |
|--------------|------------|--------------|----------------|
| 1557370 | 14 | 14 | 0 |
| 1557380 | 9 | 9 | 0 |
| 1035553 | 3 | 2 | 1 |

**14 + 9 + 2 = 25** NO_PICK rows from **3 fixtures** (2 are the Phase B upcoming NO_PICK pair; the third is historical Sheffield Utd before a successful published row).

---

## 3. Are counts all-time, current batch, league, or season?

| Surface | Published | NO_PICK | Evaluated | Pending |
|---------|-----------|---------|-----------|---------|
| **Dashboard headline** | All-time **rows** | All-time **rows** | All-time eval rows | `published − evaluated` |
| **Upcoming picks list** (`upcoming_picks`) | Upcoming **rows** (`match_date >= NOW()`, limit 50) | — | — | — |
| **Phase B report** | **Current batch**, upcoming PL 2026/27, **distinct fixtures** | Same | N/A | N/A |

| Dimension | Dashboard SQL | Phase B |
|-----------|---------------|---------|
| **Time** | All-time | First batch snapshot |
| **League** | All rows (`premier_league` only today) | `premier_league` |
| **Season** | **Not filtered** (year inferred from `match_date`) | 2026/27 upcoming API season |
| **Deduplication** | **None** (counts rows) | **Per fixture** (implicit) |

---

## 4. Breakdown by competition, season, and status

### By competition (production PostgreSQL, audit)

| `competition_key` | Published rows | NO_PICK rows |
|-------------------|----------------|--------------|
| `premier_league` | 49 | 25 |

### By match year (`EXTRACT(YEAR FROM match_date)`)

| Year | Published rows | NO_PICK rows | Interpretation |
|------|----------------|--------------|----------------|
| **2024** | 1 | 2 | Past PL 2023/24 (Sheffield Utd vs Tottenham, `fixture_id` 1035553) |
| **2026** | 48 | 23 | 2026/27 upcoming season kickoffs |

### By temporal status

| Bucket | Published rows | NO_PICK rows |
|--------|----------------|--------------|
| **Past** (`match_date < NOW()`) | 1 | 2 |
| **Upcoming** (`match_date >= NOW()`) | 48 | 23 |

### By distinct fixture (deduplicated)

| Scope | Distinct published | Distinct NO_PICK | Row published | Row NO_PICK |
|-------|-------------------|------------------|---------------|-------------|
| **All** | 49 | 3 | 49 | 25 |
| **Upcoming only** | **48** | **2** | 48 | 23 |

**Published / Evaluated / Pending**

| Metric | All-time rows | Upcoming distinct | Notes |
|--------|---------------|-------------------|-------|
| **Published** | 49 | 48 | +1 past published (1035553) |
| **Evaluated** | 1 | 0 | Only past Sheffield Utd evaluated |
| **Pending** | 48 (`49 − 1`) | 48 | All upcoming published await FT |
| **NO_PICK** | 25 rows / 3 fixtures | 2 fixtures | Row inflation from re-runs |

### By `status` column

All rows use `status = 'published'` in DDL default — both real picks and NO_PICK rows are stored with that status; **`no_prediction_flag` is the real discriminator**, not `status`.

---

## 5. Published + NO_PICK + Evaluated relationships

```
Total prediction rows = 74  (= 49 published rows + 25 NO_PICK rows)

Distinct fixtures with any prediction = 52  (49 published + 3 NO_PICK-only fixtures, with overlap on 1035553)

Evaluated rows = 1  (subset of published; FK goal_timing_evaluations.prediction_id)

Pending (dashboard) = published_rows − evaluated_rows = 49 − 1 = 48
```

**Important:** `Published + NO_PICK ≠ fixture count` because:

1. Multiple rows can exist per `fixture_id` (re-prediction inserts).
2. One fixture (1035553) has both NO_PICK history rows and one published row.
3. **Evaluated** is a separate table keyed by `prediction_id`, not mutually exclusive with NO_PICK.

**Phase B identity (upcoming batch):**

```
Distinct upcoming published (48) + distinct upcoming NO_PICK (2) = 50 upcoming fixtures touched
```

This still holds at audit time.

---

## 6. Dashboard vs API vs database — do they match?

| Field | Dashboard UI | `GET /api/goal-timing/dashboard` | PostgreSQL query |
|-------|--------------|----------------------------------|------------------|
| `published_picks` | 49 | 49 | 49 (`no_prediction_flag = false`) |
| `no_pick_count` | 25* | 25 | 25 (`no_prediction_flag = true`) |
| `evaluated_picks` | 1 | 1 | 1 (`goal_timing_evaluations`) |
| `pending_picks` | 48 | 48 | `49 − 1` (computed) |
| `upcoming_picks` (list length) | 48 | 48 | 48 rows upcoming published (limit 50) |

\*Phase 51G deploy snapshot showed **19** NO_PICK — same SQL, fewer rows before additional `/picks` traffic inflated NO_PICK duplicates.

**Verdict:** Dashboard, API, and DB **match each other**. They **do not** match Phase B because Phase B used **distinct upcoming fixtures**, not **all-time row counts**.

---

## Root-cause summary

| # | Cause | Effect on Published | Effect on NO_PICK |
|---|--------|-------------------|-----------------|
| 1 | **+1 past published row** (Sheffield Utd 1035553, 2024) | 48 → **49** | — |
| 2 | **All-time row COUNT** vs Phase B **distinct upcoming** | Hides that 48 upcoming still correct | 2 → **19/25** |
| 3 | **INSERT-only persistence** + repeated picks API | No change to distinct published upcoming (48) | **Multiplies rows** on same 2 NO_PICK fixtures (14+9) |
| 4 | **Historical NO_PICK attempts** on 1035553 | — | +2 past NO_PICK rows |

---

## Recommendations (informational only — out of scope for this audit)

Not implemented here; listed for product clarity:

1. Dashboard labels should say **“all-time rows”** or switch to **distinct fixture / latest-per-fixture** counts for parity with Phase B.
2. Separate tiles: **Upcoming batch (48+2)** vs **Historical / evaluated (1)**.
3. Long-term: upsert or one-active-prediction-per-fixture policy to stop NO_PICK row inflation.

---

## References

- `worldcup_predictor/goal_timing/dashboard_service.py` — `prediction_monitoring_counts()`
- `worldcup_predictor/goal_timing/storage/repository.py` — SQL definitions
- `EGIE_EVALUATION_PIPELINE_AUDIT.md` — Phase B 48 picks context
- `PHASE_51G_PRODUCTION_DEPLOY_REPORT.md` — dashboard deploy snapshot (19 NO_PICK at deploy time)
- Production read-only queries: 2026-06-22 on `91.107.188.229`

---

**Audit complete. No code. No deploy.**
