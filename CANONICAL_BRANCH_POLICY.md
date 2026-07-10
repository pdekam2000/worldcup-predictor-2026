# Canonical Branch Policy

Effective: 2026-07-10

## Current source-of-truth (activation phase)

```
CANONICAL_BRANCH = recovery/source-of-truth-phase6d
DEPLOYMENT_SOURCE_BRANCH = recovery/source-of-truth-phase6d
DEVELOPMENT_BASE_BRANCH = recovery/source-of-truth-phase6d
```

Approved release HEAD for forward evaluation automation: **`376620b`**

## Rationale

Unified forward evaluation canonicalization (commits `ffffcae` → `94456b7`) exists on `recovery/source-of-truth-phase6d` and is deployed to production on that branch.

`origin/main` is at `5ddac36` and does **not** yet contain `94456b7`.

```
IS_ORIGIN_MAIN_94456B7 = NO
```

## Migration to main (required for long-term policy)

When `origin/main` is the project-wide canonical source of truth:

1. Fast-forward merge: `recovery/source-of-truth-phase6d` → `main` (no force push)
2. Verify: `origin/main HEAD = production HEAD`
3. Update this document: set all three branch fields to `main`
4. Production deploys from `main` only thereafter

**Interim rule for this activation:** automation runs against the **deployment branch** (`recovery/source-of-truth-phase6d`) with aligned HEAD across local canonical worktree, origin recovery, and production.

## Parity requirement

Before timer activation:

```
LOCAL_CANONICAL_HEAD = APPROVED_GITHUB_CANONICAL_HEAD = PRODUCTION_HEAD
```

Main alignment is tracked separately; main lag does not block deployment-branch automation when deployment branch is explicitly canonical for this phase.

## Worktrees

| Path | Role |
|------|------|
| `C:\Users\kaman\Desktop\worldcup-predictor-source-recovery` | Clean canonical development |
| `C:\Users\kaman\Desktop\Footbal` | Forensic reference only (not deployment base) |
| `/opt/worldcup-predictor` | Production runtime |
