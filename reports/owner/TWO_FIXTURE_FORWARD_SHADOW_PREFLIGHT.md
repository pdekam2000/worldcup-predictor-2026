# TWO-FIXTURE FORWARD SHADOW — PREFLIGHT AUDIT

**Generated:** 2026-07-16 (local)  
**Prior research status:** `TWO_FIXTURE_PORTFOLIO_MORE_FORWARD_DATA_REQUIRED`  
**Prior validation:** 55/55 PASS

## Answers (Part A)

| # | Question | Finding |
|---|---|---|
| 1 | Forward collector code committed? | **No** — `worldcup_predictor/research/correct_score_odds/` and `two_fixture_forward_shadow/` are local/untracked relative to `origin/main` @ `435f8ee` |
| 2 | Pushed to origin/main? | **No** (HEAD matches origin, but new CS/TFPS code not in that commit) |
| 3 | Deployed to production? | **No** — production SHA still predates this package until ff-only pull after commit |
| 4 | Timer installed? | **Unit files added locally**, Install section **commented out** — not enabled |
| 5 | Timer already active? | **No** — no `worldcup-two-fixture-shadow.timer` was previously present |
| 6 | Collector vs portfolio evaluation separate? | **Yes** — jobs: `collect`, `freeze`, `evaluate`, `report` |
| 7 | Collection stops at kickoff? | **Yes** — parser rejects `fetched_at >= kickoff`; window classifier returns None for ≤0s |
| 8 | Same snapshot insert twice? | **Idempotent** — `INSERT OR IGNORE` on `correct_score_odds_lines` unique key + portfolio freeze UNIQUE |
| 9 | Same pair frozen twice? | **Prevented** — UNIQUE `(pair_id, snapshot_window, bookmaker_mode, stake_strategy, strategy_version, budget_eur)` |
| 10 | Daily pipeline invokes collection safely? | **Optional non-blocking** CS enrichment in orchestrator; TFPS cycle is a **separate** job (must not block prediction) |

## Existing assets

| Asset | State |
|---|---|
| `correct_score_odds_lines` | Present locally after cache-first ingest (~439k lines / ~136 fixtures) |
| `odds_snapshots` | Append-only; not overwritten |
| Forward plan table | `correct_score_forward_collection_plan` |
| Portfolio research engine | `two_fixture_portfolio/engine.py` |
| Real-odds ROI sample | 13 portfolios only (insufficient) |
| systemd odds refresh | `worldcup-odds-refresh.timer` (1X2-oriented; may contain CS in payloads) |
| systemd prediction daily | `worldcup-prediction-daily.timer` |
| Portfolio shadow timer | **New, disabled** |

## Critical distinction

Primary sample unit = **ONE EXECUTABLE TWO-FIXTURE PORTFOLIO**  
Not raw Correct Score odds line count.

## Safety

- No bookmaker execution path
- `betting_enabled=0` on freezes
- Process lock: `single_instance_lock("two_fixture_forward_shadow")`
- No ECSE/WDE/freeze mutation
- Timers must remain disabled until acceptance

## Recommended activation status

`TWO_FIXTURE_FORWARD_SHADOW_TIMER_DISABLED` until code is committed, production ff-only deployed, and one manual acceptance cycle passes.
