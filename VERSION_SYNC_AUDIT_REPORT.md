# VERSION SYNC AUDIT REPORT

**Phase:** PROJECT-RECOVERY — Part A  
**Date:** 2026-07-02  
**Mode:** Read-only — no changes performed

---

## Executive answers

| Question | Answer |
|----------|--------|
| Is PC code equal to GitHub? | **Yes** (same commit `7b7b08d`; PC has 4 untracked local-only files) |
| Is GitHub code equal to production? | **Yes** (same commit `7b7b08d`) |
| Can production safely pull GitHub main? | **Already synced** — no pull required today |
| Uncommitted production source drift? | **No modified tracked source** — only runtime/data + a few untracked scripts |

---

## Commit matrix

| Environment | Path | HEAD | origin/main | Status |
|-------------|------|------|-------------|--------|
| **GitHub** | `pdekam2000/worldcup-predictor-2026` | `7b7b08d` | — | Single source of truth for **code** |
| **Local PC** | `C:\Users\kaman\Desktop\Footbal` | `7b7b08d` | synced | Dev copy |
| **Production** | `/opt/worldcup-predictor` (91.107.188.229) | `7b7b08d` | synced | Live deploy |

Previous known state (outdated): production at `4dd87d2`.  
**Updated:** CODEBASE-CONSOLIDATION-2 deployed `7b7b08d` on 2026-07-01; verified again 2026-07-02.

---

## Local PC

```
Branch: main...origin/main (synced)
HEAD:   7b7b08d8d6b859cde7d356426fce4af59f667e78
Remote: https://github.com/pdekam2000/worldcup-predictor-2026.git
```

**Recent commits (local = GitHub):**
```
7b7b08d docs(consolidation-1): set final GitHub HEAD in report
b9203f3 docs(consolidation-1): update report with final commit hash
d8c9e8c docs(consolidation-1): report, config schemas, and consolidation runner fix
bbe2dd8 chore(consolidation): expand gitignore for code-first policy
8d62939 chore(tooling): project asset audit and consolidation runners
```

### Uncommitted — source (safe to commit later, not blocking)

| File | Type |
|------|------|
| `CODEBASE_CONSOLIDATION_2_DEPLOY_REPORT.md` | deploy report |
| `scripts/run_codebase_consolidation_2.py` | recovery orchestrator |
| `scripts/run_codebase_consolidation_2_production_deploy.sh` | deploy shell |
| `scripts/_db_truth_audit_readonly.py` | audit helper |
| `deployment/ecse_x2_m7_enablement_snippet.env` | **exclude** (env snippet) |

### Uncommitted — runtime / ignored (expected)

- `data/cache/resolved_seasons.json`
- `data/results/match_results.jsonl`
- `data/shadow/*.jsonl` (8 files)
- `data/validation/real_world_validation.jsonl`

**No modified tracked Python/JS source on local PC.**

---

## GitHub

- **origin/main:** `7b7b08d`
- Local is **not ahead** and **not behind**
- Repository policy: source code only (`.gitignore` excludes `data/`, `artifacts/`, credentials, `*.db`, `*.csv`)

---

## Production (Hetzner)

```
Branch: main...origin/main (synced)
HEAD:   7b7b08d
fetch origin/main: 7b7b08d
HEAD..origin/main: (empty — nothing to pull)
```

**Services:**
- `worldcup-api`: active (deployed 2026-07-01)
- `nginx`: active

### Dirty tree classification

| Category | Count (approx) | Examples | Action |
|----------|----------------|----------|--------|
| **Modified tracked source** | **0** | — | None |
| Runtime Sportmonks dumps | thousands | `data/sportmonks_dump/**` | Keep — do not reset |
| Shadow / validation jsonl | ~8 | `data/shadow/*.jsonl` | Keep |
| Artifacts (runtime) | few | `artifacts/daily_picks_*.json` | Keep |
| **Untracked source scripts** | ~3 | `scripts/eslint.critical.config.js`, `scripts/oddalerts_today_gmail_downloader.py`, `deployment/systemd/validate_phase_a19b_*.py` | Quarantine or commit to GitHub separately |
| Untracked reports | few | `ADAPTIVE_LEARNING_ACTIVATION_REPORT.md` | Local-only noise |
| Suspicious file | 1 | `C:UserskamanDesktoppostgres_backup.sql` | Review — likely accidental path on server |

**Verdict:** Dirty production tree is **runtime/data only** for tracked files. No `SOURCE_DRIFT_REVIEW_REQUIRED` for `git pull`.

---

## Sync decision

| Action | Status |
|--------|--------|
| GitHub → Production pull | **Not needed** (already at `7b7b08d`) |
| Local → GitHub push | Optional — 4 untracked recovery/deploy files |
| Local → Production | **Never** copy DB or overwrite `.env` |
| Production reset | **Do not** |

---

## Recommendation (Part A)

**READY_FOR_SAFE_CODE_SYNC** — code is already unified at `7b7b08d`.  
Next work is **pipeline + DB policy**, not emergency code deploy.

---

*Artifacts: production preflight from consolidation-2; this report supersedes VERSION sections in PROJECT_ASSET audit (2026-07-01).*
