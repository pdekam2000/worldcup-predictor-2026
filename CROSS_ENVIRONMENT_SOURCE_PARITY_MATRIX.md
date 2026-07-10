# Cross-Environment Source Parity Matrix

Date: 2026-07-10  
Approved activation HEAD: **`376620b`**

| Environment | Branch | HEAD | Clean | Ahead/Behind | Contains 376620b |
|-------------|--------|------|-------|--------------|------------------|
| Local canonical worktree | `recovery/source-of-truth-phase6d` | `376620b` | runtime shadow jsonl modified only | = origin | YES |
| GitHub `origin/recovery/source-of-truth-phase6d` | recovery | `376620b` | — | — | YES |
| GitHub `origin/main` | main | `5ddac36` | — | **behind recovery by 5 commits** | NO |
| Production `/opt/worldcup-predictor` | `recovery/source-of-truth-phase6d` | `376620b` | runtime logs modified | = origin recovery | YES |

## Critical answers

```
IS_ORIGIN_MAIN_94456b7 = NO
IS_ORIGIN_MAIN_376620b = NO
```

## Deployment-branch parity (activation scope)

```
LOCAL_CANONICAL_HEAD = APPROVED_GITHUB_CANONICAL_HEAD = PRODUCTION_HEAD = 376620b
```

## Main reconciliation (pending)

Fast-forward merge `recovery/source-of-truth-phase6d` → `main` required for long-term `origin/main` parity. No force push. Documented in `CANONICAL_BRANCH_POLICY.md`.
