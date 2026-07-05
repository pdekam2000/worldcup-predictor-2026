# FULL-PROJECT-SYNC-3 — Baseline

**Generated:** 2026-07-05 (sync start)

## Git HEAD at sync start

| Environment | HEAD | origin/main | Divergence |
|---|---|---|---|
| **Local** | `c7aedd3575f1d79860e2881d90d117fe46dfe21f` | `c7aedd3` | In sync with GitHub; large uncommitted + untracked work |
| **GitHub main** | `c7aedd3` | `c7aedd3` | — |
| **Hetzner production** | `282ef700f7bc31090f775f752f168d30e701ba24` | `c7aedd3` (after fetch) | **2 commits behind** GitHub |

## Commit range (Hetzner → GitHub)

```
282ef70 fix(odds): pass season when building DailyFixture for single-fixture refresh
71cc6a9 fix: add canonical regulation AET PEN result truth pipeline
c7aedd3 docs: add result truth source consolidation push and final report
```

## Uncommitted local changes (tracked)

- `worldcup_predictor/api/prediction_history_evaluation.py` — regulation outcome resolver fix
- `worldcup_predictor/research/ecse_live/store.py` — ECSE evaluation upsert safety
- Runtime only (exclude): `data/shadow/*`, `data/cache/*`, `data/results/*`, `data/validation/*`

## Uncommitted production changes (tracked source)

- `worldcup_predictor/api/prediction_history_evaluation.py`
- `worldcup_predictor/database/migrations.py`
- `worldcup_predictor/outcomes/*` (partial overlap with c7aedd3)
- `worldcup_predictor/research/ecse_live/evaluator.py`, `store.py`
- Plus massive runtime drift: `data/sportmonks_dump/*`, `data/shadow/*`, `data/cache/*` (exclude from sync)

## Untracked approved local source (not yet in Git)

- `worldcup_predictor/outcomes/evaluation_score_policy.py`
- `worldcup_predictor/research/ecse_historical_replay/` (full module)
- `worldcup_predictor/research/ecse_market_prior/` (full module)
- 40+ run/validate scripts for controlled predictions, ECSE research, result truth schema v8
- `tests/test_ecse_market_prior_orientation.py`
- 30+ phase reports at repo root

## Part A — Running job safety

**Status: COMPLETED**

- No active `run_*prediction*` Python processes on Hetzner
- No tmux/screen sessions
- NEXT-3 frozen predictions verified (Brazil vs Norway fixture 1568100 stored; WDE+ECSE frozen)
