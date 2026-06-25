# Phase 60C — Goal Event Backfill + Research Highlights Report

**Mode:** Backfill + research + page/API — no WDE/prediction/SaaS/shadow changes  
**Validation:** **24/24 PASS**  
**Recommendation:** **`RESEARCH_PAGE_READY`**  
**Deploy:** Ready for page + API deploy (validation passed)

---

## Part A — Goal event backfill

| Metric | Value |
|--------|------:|
| Backfill candidates (scored, no events) | 881 |
| Fixtures backfilled (this run) | 100 |
| Goal events added | 302 |
| **API calls used** | **0** |

**Sources used:** `fixture_enrichment.events_json` (API-Football shape) — cache-first, no live HTTP.

**Remaining gap:** ~781 candidates still lack goal-event minutes (mostly Bundesliga without enrichment events).

---

## Part B — First goal timing (before vs after backfill)

| Metric | Before (60B) | After (60C) | Delta |
|--------|-------------:|------------:|------:|
| Reliable fixtures | 632 | 1,032 | **+400** |
| Excluded (data missing) | 1,181 | 781 | **−400** |
| With ≥1 goal | 503 | 903 | +400 |

### Primary percentages (with ≥1 goal)

| Split | Before | After |
|-------|-------:|------:|
| First goal **1–30** | 61.23% | **62.38%** |
| First goal **31+** | 38.77% | **37.62%** |

### All reliable fixtures

| Split | Before | After |
|-------|-------:|------:|
| First goal 1–30 | 48.73% | 53.71% |
| First goal 31+ | 30.85% | 32.40% |
| No goal (0-0) | 20.41% | 13.89% |

### Minute buckets (reliable, after backfill)

| 1–15 | 16–30 | 31–45+ | 46–60 | 61–75 | 76–90+ | no_goal |
|-----:|------:|-------:|------:|------:|-------:|--------:|
| 27.2% | 21.1% | 13.0% | 7.6% | 4.8% | 3.6% | 13.9% |

The **~62 / ~38** opening-goal split (1–30 vs 31+) holds after Bundesliga enrichment backfill — consistent with Phase 60B.

---

## Part C — Odds bucket research

| Metric | Value |
|--------|------:|
| Fixtures with odds + results | **4** |

**Warning:** Local `odds_snapshots` coverage for finished matches is extremely thin. Bucket stats are illustrative only (n=1 per populated bucket). Expand odds backfill before betting-intelligence use.

Sample buckets (n=1 each): favorite win rates vary 0–100% — not statistically meaningful at this sample size.

**Future work:** Run `run_pl_odds_backfill` / cache drain when API budget allows.

---

## Part D — Research Highlights page

- **Route:** `/research/highlights` (public, no auth)
- **Style:** Dark terminal cards, green/yellow indicators, disclaimer banner
- **File:** `base44-d/src/pages/ResearchHighlights.jsx`

Cards: First Goal Timing, Minute Buckets, Odds Buckets, Data Quality.

---

## Part E — API

- **Endpoint:** `GET /api/research/highlights`
- **Module:** `worldcup_predictor/api/routes/research_highlights.py`
- **Payload:** `first_goal_distribution`, `bucket_distribution`, `odds_bucket_stats`, `data_quality`, `generated_at`
- **Safety:** No shadow, admin, WDE, or model internals exposed (validated)

---

## Part F — Artifacts

```
artifacts/phase60c_goal_event_backfill/
├── backfill_candidates.csv
├── backfill_result.json
├── first_goal_distribution_after_backfill.json
├── odds_bucket_research.csv
├── odds_bucket_summary.json
├── data_quality_report.json
└── research_highlights_cache.json
```

**Runner:** `scripts/phase60c_goal_event_backfill_research_highlights.py`  
**Validation:** `scripts/validate_phase60c_goal_event_backfill_research_highlights.py`

---

## Part G — Validation (24/24 PASS)

- Backfill candidates detected
- No duplicate overfill
- API calls counted (0)
- First-goal distribution recalculated
- Odds bucket research generated
- `/api/research/highlights` returns 200, no private fields
- `/research/highlights` page + route registered
- WDE, prediction engine, SaaS billing, admin shadow unchanged

---

## Deploy recommendation

**Deploy page + API** — validation passed. Suggested smoke after deploy:

1. `GET /api/research/highlights` → 200 with `first_goal_distribution`
2. Load `https://<domain>/research/highlights` → cards render with real sample sizes

**Do not deploy** prediction/WDE/SaaS/shadow changes (none were made).

---

## Safety confirmation

- No WDE changes
- No prediction engine changes
- No SaaS plan changes
- No Elite Shadow promotion
- **0** paid API calls in this phase

**STOP — Phase 60C complete.**
