# CODEBASE CONSOLIDATION PLAN

**Phase:** CODEBASE-CONSOLIDATION-PLAN  
**Date:** 2026-07-01  
**Scope:** Source code only — **no database migration, no DB deletion, no backup deletion**  
**Target:** `Local source = GitHub main = Production deploy source`

Supporting artifact: `artifacts/codebase_consolidation_diff_20260701.json`

---

## 1. Current split-brain state

| Environment | Path | Commit | vs `origin/main` | Code-only delta |
|-------------|------|--------|------------------|-----------------|
| **Local PC** | `C:\Users\kaman\Desktop\Footbal` | `d143e98` | **ahead 1**, behind 0 | ~490 files not on GitHub |
| **GitHub** | `pdekam2000/worldcup-predictor-2026` | `4dd87d2` | baseline | — |
| **Production** | `/opt/worldcup-predictor` | `4dd87d2` | synced with GitHub | server dirty tree is mostly **data**, not code |

### Code-only diff summary (excludes `data/`, `artifacts/`, `*.db`, `*.csv`, credentials)

| Metric | Count |
|--------|------:|
| Local code files **not on GitHub** | 490 |
| Untracked code files | 468 |
| Modified vs `origin/main` (code) | 40 |
| Local-only `scripts/` files | 184 |
| Local-only `worldcup_predictor/` files | 210 |

### Production missing modules (confirmed via SSH)

| Module | On server? |
|--------|------------|
| `worldcup_predictor/owner_daily` | **NO** |
| `worldcup_predictor/owner_predict_eval` | **NO** |
| `worldcup_predictor/owner_manual_exact` | **NO** |
| `worldcup_predictor/research/ecse_live` | **NO** |
| `scripts/evaluate_owner_knockout_predictions.py` | **NO** |

Production **matches GitHub** at `4dd87d2` but has a large dirty working tree (Sportmonks dumps, shadow jsonl, untracked scripts) — treat as **runtime data noise**, not canonical code.

---

## 2. Step 1 — Complete code-only diff

### 2.1 Local vs GitHub `main`

**Already committed locally (1 commit ahead) — `d143e98`**

Intended code in this commit (safe to publish after cleanup):

- `worldcup_predictor/data_import/historical_csv_odds.py`
- `worldcup_predictor/data_import/historical_fixture_registry.py`
- `worldcup_predictor/data_import/historical_fixture_results.py`
- `worldcup_predictor/data_import/oddalerts_gmail_exporter.py`
- `scripts/run_data_1b_csv_odds_import.py` (+ validators 1b/1c/1d)
- `scripts/oddalerts_gmail_csv_downloader.py`
- `requirements-oddalerts-gmail.txt`
- Phase DATA-1B/1C report markdown files

**BLOCKER — also in `d143e98` (must NOT push as-is):**

- `credentials/gmail_oauth_client.json` (+ client1)
- `data/backups/*.db` (~9 GB of binary DB snapshots)
- `data/imports/oddalerts_probability_exports/**/*.csv` (millions of lines)
- `data/imports/.../.gmail_token.json`
- Large `artifacts/data_1b_*.json` audit dumps

**Modified vs GitHub but uncommitted (40 code files)** — core wiring:

- `worldcup_predictor/api/main.py` — owner ECSE routes, ecse_display
- `worldcup_predictor/database/migrations.py`, `repository.py`, `connection.py`
- `worldcup_predictor/config/settings.py`
- `base44-d/src/*` — Owner Lab UI, ECSE panels (5 files)
- `worldcup_predictor/automation/.../result_refresh.py`

**Untracked code (468 files)** — bulk of owner/ECSE/WDE work:

- Entire packages: `owner_daily`, `owner_predict_eval`, `owner_manual_exact`
- ECSE research phases X2 M1–M8, X3, WC, live
- OddAlerts ECSE shadow/monitor/segment pipelines
- WDE shadow historical retrain
- ~184 new `scripts/` runners + validators

### 2.2 GitHub vs Production

| Check | Result |
|-------|--------|
| Commit hash | **Same** (`4dd87d2`) |
| Core API entry | Same `worldcup_predictor/api/main.py` (no owner ECSE routes) |
| systemd | `WorkingDirectory=/opt/worldcup-predictor`, `.env.production` |
| Code drift | **Minimal** — production is GitHub + local data modifications |

### 2.3 Local vs Production

Local is **1 commit ahead of GitHub** plus **~490 code files** never pushed. Production lacks all post-`4dd87d2` owner/ECSE modules.

---

## 3. Step 2 — Modules existing only on local

### Tier A — Owner production workflow (highest priority)

| Module | Path | Files | Purpose |
|--------|------|------:|---------|
| Owner daily cycle | `worldcup_predictor/owner_daily/` | 12 | Daily fixtures, odds import, predictions |
| Owner predict/eval | `worldcup_predictor/owner_predict_eval/` | 13 | Yesterday eval, control panel, validation |
| Owner manual exact | `worldcup_predictor/owner_manual_exact/` | 14 | Knockout WDE/ECSE attachment, eval |
| Owner euro/oddalerts | `worldcup_predictor/owner/euro_*.py`, `daily_oddalerts_*` | ~8 | UEFA/Euro odds pipelines |
| Owner scripts | `scripts/run_owner_*`, `evaluate_owner_*`, `validate_owner_*` | ~35 | CLI entrypoints |

### Tier B — ECSE / OddAlerts research → production

| Module | Path | Files |
|--------|------|------:|
| ECSE live snapshots | `worldcup_predictor/research/ecse_live/` | 13 |
| ECSE WC / knockout risk | `worldcup_predictor/research/ecse_wc/` | 3 |
| ECSE X2 M1–M8 | `worldcup_predictor/research/ecse_x2_m*/` | ~44 |
| ECSE X3 composite | `worldcup_predictor/research/ecse_x3/` | 7 |
| ECSE X3-B owner lab | `worldcup_predictor/research/ecse_x3_b/` | 8 |
| OddAlerts ECSE shadow | `worldcup_predictor/research/oddalerts_ecse_*.py` | ~8 |
| ECSE API routes | `worldcup_predictor/api/routes/owner_ecse_*.py`, `ecse_display.py` | 4 |

### Tier C — Data import / historical CSV (code only)

| Module | Path | Files |
|--------|------|------:|
| Extended data_import | `worldcup_predictor/data_import/` | 24 |
| External historical zip | `external_historical_*.py` | 4 |
| OddAlerts CSV promotion | `oddalerts_csv_*.py` | 6 |
| DATA-1 scripts | `scripts/run_data_1*`, `validate_data_1*` | ~20 |

### Tier D — WDE shadow retrain

| Module | Path | Files |
|--------|------|------:|
| WDE shadow historical | `worldcup_predictor/research/wde_shadow_historical/` | 13 |
| WDE shadow scripts | `scripts/train_wde_shadow_*`, `run_wde_shadow_*` | ~10 |

### Tier E — Frontend Owner Lab

| Path | Notes |
|------|-------|
| `base44-d/src/pages/owner/OwnerEcseShadowLab.jsx` | New |
| `base44-d/src/pages/owner/OwnerEcseOddalertsShadow.jsx` | New |
| `base44-d/src/components/match-center/EcseExactScorePanel.jsx` | New |
| `base44-d/src/App.jsx`, `ownerNavConfig.js`, etc. | Modified |

### Tier F — Docs / reports (optional for GitHub)

~80 `*_REPORT.md` files at repo root — valuable for history but not required for runtime. Recommend separate `docs/reports/` batch or gitignore.

---

## 4. Step 3 — Safe commit batches

**Principle:** Each batch = reviewable, imports cleanly, no secrets, no binaries, no CSV/data.

### Batch 0 — Hygiene (before any push)

**Do first.** Fix the existing unpushed commit `d143e98` — it contains secrets and binaries.

```bash
# DO NOT push d143e98 as-is

# 1) Expand .gitignore (see Section 6)
# 2) Remove from index (keep files on disk):
git rm -r --cached credentials/ data/backups/ data/imports/oddalerts_probability_exports/ 2>/dev/null || true
git rm --cached artifacts/data_1b_*.json artifacts/_oddalerts_csv_audit.json 2>/dev/null || true

# 3) Option A — soft reset and recommit cleanly:
git reset --soft origin/main
# Stage ONLY code files per batches below

# Option B — new branch from origin/main, cherry-pick code hunks only
git checkout -b consolidation/clean-main origin/main
```

**Never commit:** `.env`, `credentials/`, `*.db`, `data/oddalerts_csv/`, `data/backups/`, `.gmail_token.json`, `artifacts/*.json` (generated)

### Batch 1 — Database layer + settings (foundation)

```
worldcup_predictor/database/migrations.py
worldcup_predictor/database/repository.py
worldcup_predictor/database/connection.py
worldcup_predictor/database/sqlite_retry.py
worldcup_predictor/config/settings.py
worldcup_predictor/config/euro_feed_registry.py
worldcup_predictor/config/league_registry.py
```

Message: `feat(db): migrations and repository for ECSE/owner tables`

### Batch 2 — Core data_import (historical + oddalerts code)

```
worldcup_predictor/data_import/historical_*.py
worldcup_predictor/data_import/oddalerts_*.py
worldcup_predictor/data_import/external_historical_*.py
worldcup_predictor/data_import/european_*.py
requirements-oddalerts-gmail.txt
scripts/run_data_1*.py
scripts/validate_data_1*.py
scripts/oddalerts_gmail_csv_downloader.py
```

Message: `feat(data-import): historical CSV and OddAlerts import pipelines`

### Batch 3 — ECSE research core

```
worldcup_predictor/research/ecse_live/
worldcup_predictor/research/ecse_training_dataset.py
worldcup_predictor/research/ecse_lambda_extraction.py
worldcup_predictor/research/ecse_score_distribution.py
worldcup_predictor/research/ecse_exact_score_backtest.py
worldcup_predictor/research/ecse_dixon_coles_distribution.py
worldcup_predictor/research/ecse_match_display.py
+ matching scripts/run_ecse_1*.py and validate_ecse_1*.py
```

Message: `feat(ecse): live snapshot engine and ECSE-1 research pipeline`

### Batch 4 — ECSE X2/X3 + OddAlerts shadow

```
worldcup_predictor/research/ecse_x2_m*/
worldcup_predictor/research/ecse_x3/
worldcup_predictor/research/ecse_x3_b/
worldcup_predictor/research/ecse_wc/
worldcup_predictor/research/oddalerts_ecse_*.py
worldcup_predictor/research/oddalerts_ecse_*_ddl.py
+ scripts/run_ecse_x2_* and validate_ecse_x2_*
+ scripts/write_ecse_oddalerts_shadow_predictions.py
```

Message: `feat(ecse-x2/x3): shadow labs and OddAlerts ECSE integration`

### Batch 5 — WDE shadow historical

```
worldcup_predictor/research/wde_shadow_historical/
worldcup_predictor/research/wde_shadow_*.py
scripts/train_wde_shadow_model_from_historical_csv.py
scripts/run_wde_shadow_*.py
scripts/validate_wde_shadow_*.py
```

Message: `feat(wde): historical CSV shadow retrain pipeline`

### Batch 6 — Owner daily + predict/eval + manual exact

```
worldcup_predictor/owner_daily/
worldcup_predictor/owner_predict_eval/
worldcup_predictor/owner_manual_exact/
worldcup_predictor/owner/daily_oddalerts_*.py
worldcup_predictor/owner/euro_*.py
worldcup_predictor/owner/wc_owner_eval_summary.py
worldcup_predictor/owner/oddalerts_ecse_lab_service.py
+ scripts/run_owner_*.py
+ scripts/evaluate_owner_*.py
+ scripts/validate_owner_*.py
+ scripts/owner_today_10_exact_scores.py
```

Message: `feat(owner): daily prediction, eval, and knockout exact-score workflow`

### Batch 7 — API routes + automation wiring

```
worldcup_predictor/api/main.py
worldcup_predictor/api/routes/owner_ecse_*.py
worldcup_predictor/api/routes/ecse_display.py
worldcup_predictor/api/routes/admin_ecse_x2_shadow.py
worldcup_predictor/automation/worldcup_background/result_refresh.py
worldcup_predictor/clients/api_football.py
worldcup_predictor/providers/sportmonks_fixture_lookup.py
worldcup_predictor/quota/local_first.py
worldcup_predictor/autonomous/orchestrator.py
```

Message: `feat(api): owner ECSE routes and result refresh automation`

### Batch 8 — Frontend Owner Lab

```
base44-d/src/pages/owner/
base44-d/src/components/match-center/EcseExactScorePanel.jsx
base44-d/src/App.jsx
base44-d/src/api/worldcupApi.js
base44-d/src/lib/ownerNavConfig.js
(+ other modified base44-d/src files)
```

Message: `feat(frontend): Owner ECSE shadow lab and exact score UI`

### Batch 9 — Tooling, audit, docs (optional)

```
scripts/run_project_asset_audit.py
scripts/validate_project_asset_audit.py
scripts/_codebase_consolidation_analyze.py
PROJECT_ASSET_DATABASE_GITHUB_AUDIT_REPORT.md
CODEBASE_CONSOLIDATION_PLAN.md
docs/reports/*.md  (move root *\_REPORT.md here)
```

Message: `docs: asset audit and consolidation tooling`

---

## 5. Step 4 — Push missing code to GitHub

**Status:** Planned — **not executed in this phase.**

### Pre-push checklist

- [ ] Batch 0 complete — no credentials, DBs, or CSV in commits
- [ ] `.gitignore` updated (Section 6)
- [ ] Local tests: `python -m compileall worldcup_predictor` (smoke)
- [ ] Review diff size per batch (< 500 files each)
- [ ] Confirm GitHub repo size limits (avoid 2M+ line CSV commits)

### Push sequence

```bash
# After batches committed on branch consolidation/clean-main:
git fetch origin
git log --oneline origin/main..HEAD   # review commits

# Push feature branch first (safer than direct main):
git push -u origin consolidation/clean-main

# Open PR → review → merge to main
gh pr create --title "Codebase consolidation: owner + ECSE + WDE shadow" \
  --body "Code-only sync from local. No DB/data migration."

# After merge:
git checkout main
git pull origin main
git tag codebase-consolidation-20260701
git push origin codebase-consolidation-20260701
```

### If `d143e98` must be preserved

Use `git rebase -i origin/main` or `git filter-repo` to strip binaries/secrets from history **before** any push. Do not force-push `main` without owner approval.

---

## 6. `.gitignore` additions (before Batch 0)

Add to `.gitignore`:

```gitignore
# Data & generated (code-first policy)
data/
!data/.gitkeep
artifacts/
reports/
logs/
models/
credentials/
*.db
*.sqlite
*.sqlite3
*.csv
*.jsonl
.cache/

# Secrets & tokens
**/.gmail_token.json
**/gmail_oauth_client*.json

# Temp audit helpers
scripts/_audit_*.py
scripts/_codebase_consolidation_analyze.py
```

Keep code; exclude runtime/generated assets.

---

## 7. Step 5 — Deployment plan (GitHub → Production)

**Scope:** Code deploy only. **Do not replace production DB** in this phase.

### 7.1 Pre-deploy

| Step | Action |
|------|--------|
| 1 | Merge consolidation PR to `origin/main` |
| 2 | On server: `cd /opt/worldcup-predictor && git stash push -m "pre-consolidation-data" -- data/ artifacts/` |
| 3 | Record pre-deploy commit: `git rev-parse HEAD > /tmp/pre_consolidation_commit.txt` |
| 4 | Backup `.env.production` (copy, do not commit) |

### 7.2 Deploy commands (maintenance window)

```bash
ssh root@91.107.188.229

cd /opt/worldcup-predictor
git fetch origin
git checkout main
git pull origin main   # after GitHub updated

# Python deps
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-oddalerts-gmail.txt  # if added

# DB schema only (no data copy) — run migrations
python -c "from worldcup_predictor.database.migrations import run_migrations; run_migrations()"

# Frontend rebuild
cd base44-d && npm ci && npm run build
# Copy dist to nginx docroot per existing deploy script

# Restart API (after verification)
systemctl restart worldcup-api
systemctl status worldcup-api --no-pager
curl -s http://127.0.0.1:8000/api/health
```

### 7.3 Post-deploy verification

| Check | Command / expectation |
|-------|----------------------|
| Commit match | `git rev-parse HEAD` == GitHub main |
| Owner modules present | `test -d worldcup_predictor/owner_manual_exact` |
| API routes load | `curl /api/health`; no import errors in journal |
| ECSE tables exist | migrations applied; **empty tables OK** until DB phase |
| Frontend Owner Lab | `/owner/ecse-shadow-lab` loads |
| Production DB untouched | `data/football_intelligence.db` size unchanged |

### 7.4 Rollback

```bash
cd /opt/worldcup-predictor
git checkout $(cat /tmp/pre_consolidation_commit.txt)
systemctl restart worldcup-api
git stash pop   # restore data dirty tree if needed
```

### 7.5 What NOT to do in code deploy

- Do not `scp` local `football_intelligence.db` over production
- Do not delete `data/backups/` on either side
- Do not run owner daily pipelines against production until DB strategy approved

---

## 8. Three-way sync target timeline

| Phase | Action | DB impact |
|-------|--------|-----------|
| **Now** | Batches 0–9 → GitHub | None |
| **Next** | Deploy code to production | Schema migrate only |
| **Later** | DATABASE-CONSOLIDATION phase | Explicit sync plan |

---

## 9. Risk register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Push `d143e98` with 9GB DB + credentials | **Critical** | Batch 0 reset before push |
| `credentials/` tracked in git | **High** | Remove from index; rotate tokens |
| Production missing ECSE tables | Medium | Run migrations after code deploy |
| Local/server DB divergence | Medium | Defer to DB phase; code-first |
| 184 scripts overwhelm review | Medium | Batch by domain; PR per batch |
| Server dirty tree conflicts on pull | Low | Stash `data/` before pull |

---

## 10. Final recommendation

**Proceed with code consolidation in ordered batches. Do not push until Batch 0 removes secrets and binaries from commit history.**

Priority order:

1. **Batch 0** — fix `.gitignore`, strip bad files from `d143e98`
2. **Batches 1–2** — DB layer + data_import (foundation)
3. **Batches 6–7** — owner workflow + API (business critical)
4. **Batches 3–5** — ECSE/WDE research
5. **Batch 8** — frontend
6. **Deploy to production** after GitHub main updated
7. **Database consolidation** — separate phase after code parity achieved

**Success criteria:**

```
git rev-parse HEAD          # same on local (after push), GitHub, production
test -f worldcup_predictor/owner_manual_exact/knockout_evaluation.py  # all three
# football_intelligence.db unchanged on production after deploy
```

---

*Generated from read-only analysis. No commits, pushes, deploys, or database changes were performed in this phase.*
