# PROJECT RECOVERY — MASTER REPORT

**Phase:** PROJECT-RECOVERY  
**Date:** 2026-07-02  
**Mode:** Audit + Plan only — **no implementation performed**

---

## Final recommendation

### **FULL_RECOVERY_READY**

Source code is unified. Production DB is protected and canonical.  
Remaining work is **pipeline automation on production** and optional **selective data import** — not emergency sync.

Sub-status flags:
- Code sync: **READY_FOR_SAFE_CODE_SYNC** (already at `7b7b08d`)
- Source drift: **Clear** (no blocking drift)
- DB merge: **NEED_DB_IMPORT_PLAN** (only if you want local research rows on prod)
- Automation: **NEED_PIPELINE_IMPLEMENTATION**

---

## 1. Version sync status

| Environment | Commit | = GitHub? |
|-------------|--------|-----------|
| GitHub `main` | `7b7b08d` | — |
| Local PC | `7b7b08d` | Yes |
| Production Hetzner | `7b7b08d` | Yes |

**Are PC / GitHub / Hetzner equal?**  
**Yes for source code.**  
Local has 4 untracked recovery files + runtime jsonl. Production has runtime Sportmonks/shadow dirty tree only.

Detail: `VERSION_SYNC_AUDIT_REPORT.md`

---

## 2. Database truth status

| DB | Role | Size | Predictions | Evaluations |
|----|------|------|-------------|-------------|
| Production SQLite | **CANONICAL live** | 9.5 GB | 48 | 19 |
| Production PostgreSQL | **CANONICAL users/billing** | — | via SaaS | — |
| Local SQLite | **DEV / research** | 31.3 GB | 185 | 35 |

**Safest source of truth:**
- **Code:** GitHub `main`
- **Production data:** Hetzner DBs only
- **Local PC:** development copy — never push DB to server

Detail: `DATABASE_TRUTH_AUDIT_REPORT.md`

---

## 3. What must be synced

| Item | Action | Priority |
|------|--------|----------|
| GitHub → Production code | **Done** | — |
| Local recovery reports → GitHub | Optional commit | Low |
| Owner daily cron on production | Enable scheduler | **High** |
| Eval result refresh timer | Enable on production | **High** |
| Local shadow predictions → prod | Selective import plan | Medium (optional) |
| Local 31GB DB → prod | **Never** | Forbidden |

---

## 4. What must NEVER be overwritten

- Production `data/football_intelligence.db`
- Production PostgreSQL
- `.env.production` / credentials
- Production backups under `data/backups/`
- Runtime dumps (`sportmonks_dump/`, shadow jsonl)
- Git history via force reset without audit

---

## 5. Full prediction / evaluation / learning pipeline

| Stage | Status |
|-------|--------|
| Discover fixtures | PARTIAL — manual/cron |
| Generate predictions | EXISTS — not scheduled on prod |
| Store predictions | EXISTS — prod under-populated (48 rows) |
| Sync results | EXISTS — not continuous |
| Evaluate | EXISTS — manual + opt-in timers |
| Dashboard | EXISTS — Owner Lab UI |
| Learning / retrain | PARTIAL — advisory only |

**User-visible gap:** Predictions like USA 2-0 and France 3-0 were **correct** but formal eval did not run because result sync + eval cron are not fully automated on production.

Detail: `FULL_AUTO_PIPELINE_AUDIT_REPORT.md`

---

## 6. Implementation plan (awaiting approval)

### Phase 1 — Source code (DONE)
GitHub `main` → production at `7b7b08d`.  
Optional: commit recovery docs/scripts to GitHub.

### Phase 2 — Canonical DB protection
- Nightly SQLite snapshot on Hetzner (retain 7 days)
- Record schema version + row counts daily
- Lock policy: no full DB replace without signed import plan

### Phase 3 — All-match scheduler (production)
- Install systemd timer for `run_daily_owner_prediction_cycle.py`
- Competitions: WC + subscribed European leagues
- Log to `data/logs/owner_daily/`
- Store all preds to `worldcup_stored_predictions`

### Phase 4 — Result sync
- Enable `worldcup-evaluate-results.timer` OR owner result_sync in same timer chain
- Refresh API-Football finished fixtures every 30 min
- Upsert `fixture_results`

### Phase 5 — Evaluation engine
- Chain after result sync: `worldcup-auto-evaluation` + `run_owner_daily_prediction_and_eval.py`
- Markets: 1X2, BTTS, O/U 2.5, correct score, DC, goal timing (EGIE), ECSE where attached
- Copy `artifacts/manual_owner_exact_score_predictions_*.json` to production for knockout eval

### Phase 6 — Learning loop (advisory first)
- Keep `WDE_RETRAINED: False` until owner approval gate
- Enable learning capture + weekly self-learning report
- Adaptive confidence stays on (already in scoring path)
- ECSE/EGIE shadow: monitor only until promotion criteria met

### Phase 7 — Owner dashboard
- Add “today’s predictions / waiting eval / evaluated / accuracy” panel
- Surface provider coverage gaps
- Show last 30/100 eval results from `worldcup_prediction_evaluations`

---

## 7. Recommended next Cursor command

After you approve this plan, run:

```
PHASE PROJECT-RECOVERY-IMPLEMENT-1

Enable production owner-daily + eval systemd timers only.
Do not copy local DB.
Backup production SQLite first.
Verify USA/Bosnia and France/Sweden evaluations appear in owner report.
Produce OWNER_PIPELINE_ENABLEMENT_REPORT.md
```

---

## 8. Report index

| Report | Purpose |
|--------|---------|
| `VERSION_SYNC_AUDIT_REPORT.md` | Part A — git parity |
| `DATABASE_TRUTH_AUDIT_REPORT.md` | Part B — DB canonical decision |
| `CODE_SYNC_DEPLOY_REPORT.md` | Part C — deploy status + template |
| `FULL_AUTO_PIPELINE_AUDIT_REPORT.md` | Part D — predict/eval/learning |
| `PROJECT_RECOVERY_MASTER_REPORT.md` | This file |

Prior work still valid:
- `CODEBASE_CONSOLIDATION_PLAN.md`
- `CODEBASE_CONSOLIDATION_1_REPORT.md`
- `CODEBASE_CONSOLIDATION_2_DEPLOY_REPORT.md`
- `PROJECT_ASSET_DATABASE_GITHUB_AUDIT_REPORT.md` (superseded for version section)

---

## 9. One-page clarity for the user

You were confused because **four things got mixed**:
1. **Code** — now **aligned** (GitHub = PC = Hetzner at `7b7b08d`)
2. **Database** — **not aligned** (local 31GB research DB vs production 9.5GB live DB) — **this is OK** if production stays canonical
3. **Predictions** — models **do work** (USA 2-0, France 3-0 confirmed) but **automation** does not run eval on schedule
4. **Learning** — data is captured but **does not auto-retrain** by design

**Nothing destructive was done in this audit.**

---

*Generated read-only. Approve implementation plan before Phase 1–7 execution.*
