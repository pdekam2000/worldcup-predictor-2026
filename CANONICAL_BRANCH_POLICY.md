# Canonical Branch Policy

Effective: 2026-07-10 (updated after main reconciliation)

## Source of truth

```
CANONICAL_BRANCH = main
DEPLOYMENT_SOURCE_BRANCH = main
DEVELOPMENT_BASE_BRANCH = main
```

## Release baseline

```
CANONICAL_COMMIT_SHA = f7cfd4a1166f6846680c53fec23e1b7e7d794392
```

## Branch roles

| Branch | Role |
|--------|------|
| `main` | Canonical source, deployment, and development base |
| `recovery/source-of-truth-phase6d` | Historical integration branch; HEAD equals `main` after fast-forward |
| `Footbal/` workspace | Forensic reference only — never deployment base |

## Parity requirement

```
LOCAL_CLEAN_HEAD = origin/main HEAD = PRODUCTION_HEAD = f7cfd4a
```

## Worktrees

| Path | Role |
|------|------|
| `C:\Users\kaman\Desktop\worldcup-predictor-source-recovery` | Clean canonical development (track `main`) |
| `C:\Users\kaman\Desktop\Footbal` | Forensic only |
| `/opt/worldcup-predictor` | Production runtime on `main` |

## Rules

- No force push to `main`
- Runtime DB, secrets, caches, logs never committed
- Forward evaluation authority: `data/evaluation/forward_prediction_tracking.db` (runtime only)
- Automation timers remain enabled per activation phase
