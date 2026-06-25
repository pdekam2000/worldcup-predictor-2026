# Phase 60B — First Goal Timing Distribution Report

**Mode:** Research only — no deploy, no prediction/WDE/public/SaaS changes  
**Generated:** 2026-06-25  
**Recommendation:** **`USE_1_30_PRIOR`**

---

## Executive answer

Across **632 reliable completed fixtures** with trustworthy first-goal timing (or confirmed 0-0):

| Cohort | First goal 1–30 | First goal 31+ | No goal |
|--------|----------------:|---------------:|--------:|
| **A) Fixtures with ≥1 goal** (n=503) | **61.23%** (308) | **38.77%** (195) | — |
| **B) All reliable fixtures** (n=632) | **48.73%** (308) | **30.85%** (195) | **20.41%** (129) |

**Main question:** Among matches that had at least one goal, **~61%** saw the first goal in minutes **1–30**; **~39%** after minute 30.

The split is remarkably stable across independent data sources (SQLite goal events, EGIE backtest JSONL, UEFA survival parquet): all cluster near **61% / 39%** for the with-goal cohort.

---

## Scope and data sources

| Source | Role | Reliable rows | With goal | 1–30% (with goal) |
|--------|------|--------------:|----------:|------------------:|
| `fixture_goal_events` (SQLite) | Primary per-event minutes | 359 | 359 | 61.0% |
| `phase51h_egie_backtest.jsonl` | Premier League EGIE replay | 359 | 349 | 61.32% |
| `uefa_survival_dataset.parquet` | UEFA club (Sportmonks subset) | 186 | 134 | 61.19% |
| `api_response_cache` | Cached API-Football events | 10 | 10 | 70.0% |
| `sqlite_results_only` | Confirmed 0-0, no events | 77 | 0 | — |

- **Database:** `data/football_intelligence.db`
- **Finished fixtures in DB:** 1,813 (with results)
- **Reliable for timing analysis:** 632
- **Excluded (`data_missing`):** 1,181 — scored matches with no goal-event minute data
- **API calls used:** **0** (cache/DB only)

Fixture-level deduplication prefers rows with goal-event timing over results-only rows.

---

## Detailed minute buckets (reliable fixtures, n=632)

| Bucket | Count | % of reliable |
|--------|------:|--------------:|
| **1–15** | 175 | 27.69% |
| **16–30** | 133 | 21.04% |
| **31–45+** | 78 | 12.34% |
| **46–60** | 54 | 8.54% |
| **61–75** | 31 | 4.91% |
| **76–90+** | 32 | 5.06% |
| **no_goal** | 129 | 20.41% |

Early-half concentration: **48.73%** of all reliable fixtures see the first goal by minute 30 (including 0-0 as neither bucket).

---

## Breakdown by competition

| League / tournament | Reliable | With goal | 1–30% (with goal) | 31+% (with goal) | No goal % |
|---------------------|----------:|----------:|------------------:|-----------------:|----------:|
| **Premier League** | 370 | 359 | 61.0% | 39.0% | 2.97% |
| **Champions League** | 89 | 58 | 62.07% | 37.93% | 34.83% |
| **Conference League** | 65 | 51 | 62.75% | 37.25% | 21.54% |
| **Europa League** | 32 | 25 | 56.0% | 44.0% | 21.88% |
| **Bundesliga** | 66 | 0 | — | — | 100%* |
| **World Cup 2026** | 0 | 0 | — | — | — |

\*Bundesliga: only **66 confirmed 0-0** fixtures have reliable classification locally; **1,166 scored Bundesliga fixtures lack goal-event data** and are excluded from percentages. Do not interpret Bundesliga league stats from this run.

**UEFA club tournaments** (merged parquet + SQLite): first-goal 1–30 split aligns with global ~61/39 among scored matches, but higher no-goal rates in knockout contexts (UCL 34.83% 0-0 in reliable sample).

**World Cup:** No completed fixtures with goal-event timing in local DB yet (5 fixtures `data_missing`).

---

## Breakdown by season

| Season | Reliable | With goal | 1–30% (with goal) | No goal % | Notes |
|--------|----------:|----------:|------------------:|----------:|-------|
| **2023** | 383 | 359 | 61.0% | 6.27% | Premier League — best coverage |
| **unknown** | 196 | 144 | 61.81% | 26.53% | Mostly UEFA parquet rows |
| **2021–2022, 2024** | 15–22 each | 0 | — | 100% | Bundesliga 0-0 only; no event data |

---

## First goal by side (fixtures with timing, n=369)

| Side | Count | 1–30% | 31+% |
|------|------:|------:|-----:|
| **Home** | 199 | 61.31% | 38.69% |
| **Away** | 160 | 60.62% | 39.38% |
| **Unknown** | 10 | 70.0% | 30.0% |

Home and away first-goal timing distributions are effectively identical; no material home-first-goal timing bias in this sample.

---

## Data quality

| Metric | Value |
|--------|------:|
| Fixtures skipped (scored, no events) | 1,181 |
| Score vs event inconsistencies | 0 |
| Goal events with missing minute | 0 |
| Duplicate events deduped | 0 |

### Source reliability ranking

1. **`sqlite_goal_events`** — highest; per-event minute + `sort_index`, validated against scores
2. **`egie_backtest_jsonl`** — Premier League EGIE replay with `actual_first_goal_minute`
3. **`uefa_survival_parquet`** — Sportmonks UEFA club subset
4. **`sqlite_results_only`** — 0-0 confirmation only; no timing
5. **`data_missing`** — excluded from percentage denominators

### Warnings

1. **Large coverage gap:** 65% of finished fixtures (1,181 / 1,813) cannot be timed — overwhelmingly Bundesliga bulk import without `fixture_goal_events`.
2. **Bundesliga league breakdown is misleading** until goal events are backfilled.
3. **Sample is PL + UEFA-heavy** — global prior is well-supported for those competitions; World Cup historical data not present locally.
4. **No live API calls** — production PostgreSQL was not queried; local SQLite + artifacts only.

---

## EGIE goal timing model recommendation

### **`USE_1_30_PRIOR`**

**Rationale:**

- Among scored matches, **~61% / ~39%** (1–30 vs 31+) is consistent across three independent sources.
- League-level splits for Premier League and UEFA club competitions do not diverge materially from the global split (all within ~2 pp of 61%).
- Home vs away shows no meaningful timing skew.
- A single global 1–30 prior is a sound EGIE baseline; league-specific priors are **not required** at current evidence strength.

**Not recommended:**

- `USE_LEAGUE_SPECIFIC_PRIORS` — insufficient cross-league variance in available timed data.
- `NEEDS_MORE_DATA` — 503 scored fixtures with timing is adequate for a coarse binary prior, though Bundesliga/WC backfill would improve breadth.
- `BLOCKED_WITH_REASON` — not blocked; research completed with caveats above.

**Suggested EGIE parameters (informational only — no engine changes made):**

- P(first goal ≤ 30 | ≥1 goal) ≈ **0.61**
- P(first goal > 30 | ≥1 goal) ≈ **0.39**
- P(no goal) ≈ **0.20** among reliable completed fixtures (competition-dependent; PL ~3%, UEFA higher)

---

## Artifacts

```
artifacts/phase60b_first_goal_timing_distribution/
├── first_goal_timing_rows.csv
├── first_goal_timing_summary.json
├── first_goal_timing_by_league.csv
├── first_goal_timing_by_season.csv
└── data_quality_report.json
```

**Runner:** `scripts/phase60b_first_goal_timing_distribution.py`  
**Module:** `worldcup_predictor/research/first_goal_timing_distribution.py`

---

## Safety confirmation

- No prediction engine changes
- No WDE changes
- No public prediction changes
- No SaaS plan changes
- No deploy
- **0** paid API calls

**STOP — Phase 60B complete.**
