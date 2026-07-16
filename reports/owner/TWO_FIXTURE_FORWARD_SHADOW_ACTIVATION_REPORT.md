# TWO-FIXTURE FORWARD SHADOW — ACTIVATION REPORT

**Final status:** `TWO_FIXTURE_FORWARD_SHADOW_TIMER_DISABLED`

**Generated:** 2026-07-16T04:43:00Z (local acceptance cycle)

## Executive summary

The forward shadow program is **implemented and runnable locally** under an exclusive process lock.  
A manual cycle froze **36** hypothetical portfolios (6 stake strategies × 2 bookmaker modes × 3 snapshot windows) for Cohort **A**.  

**Timers are intentionally disabled** until code is committed, pushed, production `git pull --ff-only` completes, and owner acceptance is recorded.  
**No betting path exists.** Stakes are labelled hypothetical.

## Answers (Part T)

| # | Question | Answer |
|---|---|---|
| 1 | Collector deployed? | **Code ready locally; not on production** until commit + ff-only deploy |
| 2 | Scheduled? | **No** — systemd timer Install section commented out |
| 3 | Providers active? | API-Football / SportMonks CS via `odds_snapshots` → `correct_score_odds_lines` (cache-first) |
| 4 | Bookmakers covered? | Those present in extracted CS lines (see `bookmaker_coverage.csv`) |
| 5 | Prematch + 90-minute? | **Yes** — live/ET/1H rejected; `CORRECT_SCORE_90_MINUTES` |
| 6 | Fixtures with complete Top5 pricing? | Varies; freezes require ≥10 priced primary combos |
| 7 | Eligible fixture pairs today? | Primary gate produced 1 selected pair (highest_expected_joint) when ECSE+CS available |
| 8 | Portfolios frozen? | **36** |
| 9 | Portfolios completed (evaluated)? | **0** (kickoffs still future → RESULT_PENDING) |
| 10 | Primary hit rate? | N/A until completions |
| 11 | Hedge-enhanced hit rate? | N/A until completions |
| 12 | Equal Gross Return ROI? | N/A until completions |
| 13 | Minimax ROI? | N/A until completions |
| 14 | Full-loss rate? | N/A until completions |
| 15 | Stake-recovery rate? | N/A until completions |
| 16 | Same-bookmaker portfolios? | **18** freezes |
| 17 | Cross-bookmaker theoretical? | **18** freezes (separate stream) |
| 18 | Max drawdown? | N/A until completions |
| 19 | Strategy version frozen? | `tfps-v1` |
| 20 | Cohort active? | **A** (first 100 completed) |
| 21 | Remaining to 100 milestone? | **100** completed portfolios |
| 22 | Timers/locks healthy? | Lock works; timer **disabled by design** |
| 23 | Betting action possible? | **No** (`betting_action_possible=false`) |
| 24 | Models/freezes preserved? | **Yes** — read-only ECSE snapshots; no WDE/ECSE formula changes; no historical freeze mutation |
| 25 | Exact next review milestone? | **100 completed evaluated portfolios** → EARLY_EDGE_SIGNAL / EARLY_NO_EDGE_SIGNAL / INCONCLUSIVE |

## Architecture delivered

### Jobs (separate)

1. `collect` — cache-first CS extraction + forward plan (stops at kickoff)
2. `freeze` — eligibility → pair selection (gate locked) → immutable portfolio freezes
3. `evaluate` — regulation-time results → ROI from **frozen** odds/stakes only
4. `report` — daily / weekly / monthly owner reports

### Modes (never merged)

- `SINGLE_BOOKMAKER_EXECUTABLE`
- `CROSS_BOOKMAKER_THEORETICAL`

### Snapshot windows

`FIRST_AVAILABLE` · `APPROX_24H` · `APPROX_6H` · `APPROX_1H` · `FINAL_PREMATCH`  
(with documented tolerances; post-kickoff rejected)

### Hedge policy (frozen)

- Primary: canonical Top6–Top10
- Secondary: complementary +1/+1
- Max standard hedges: **5**
- Canonical Top5 **unchanged**

### Stake strategies (parallel virtual portfolios)

EQUAL · EQUAL_GROSS_RETURN (benchmark) · MINIMAX · PROBABILITY_WEIGHTED · POSITIVE_EDGE_ONLY · TIERED_PRIMARY_HEDGE

### Cohort locking

- Cohort A: first 100 completed — no mid-cohort strategy changes
- Cohort B: next 400
- Cohort C: untouched confirmation

## Scheduling (not enabled)

| Unit | State |
|---|---|
| `deployment/systemd/worldcup-two-fixture-shadow.service` | Present; Install commented |
| `deployment/systemd/worldcup-two-fixture-shadow.timer` | Present; Install commented; 4× daily calendars prepared |

**Do not** `systemctl enable` until acceptance checklist in the timer unit passes.

## Manual run

```bash
python scripts/run_two_fixture_forward_shadow_cycle.py --jobs all
python scripts/validate_two_fixture_forward_shadow_collection.py
```

## Observability (local after cycle)

- Health: `FORWARD_COLLECTION_PARTIAL` (frozen but not yet completed)
- Unit of sample: **ONE_EXECUTABLE_TWO_FIXTURE_PORTFOLIO**
- CS fixtures with prematch lines: 136
- Frozen: 36 · Completed: 0 · To 100: 100

## Owner retrieval (read-only)

Supports future owner questions for today’s package, yesterday’s result, weekly ROI, cohort A, collector status — **never creates or places a bet**.

## Production deploy checklist (later)

1. Commit TFPS + CS odds packages  
2. Push to `origin/main`  
3. Production: `git pull --ff-only`  
4. Backup DB metadata / odds / freezes / env  
5. Manual acceptance cycle on production  
6. Validate script PASS  
7. Only then enable timer  

## Constraints respected

- No automatic betting  
- No bookmaker account integration  
- No ECSE/WDE formula changes  
- No historical freeze mutation  
- No synthetic odds in ROI  
- No timer enablement yet  

## Final status

`TWO_FIXTURE_FORWARD_SHADOW_TIMER_DISABLED`

STOP.
