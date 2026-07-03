# CLAUDE Access Checklist — WorldCup Predictor

**Phase:** CLAUDE-OPS-1  
**Purpose:** Verify Claude can safely develop locally and inspect production.

---

## 1. GitHub / local access

Run from project root (`C:\Users\kaman\Desktop\Footbal` or `/opt/worldcup-predictor`):

```bash
git status -sb
git rev-parse HEAD
git rev-parse origin/main
git log --oneline -5
```

**Expected:** Clean or runtime-only dirty tree; `HEAD` matches `origin/main` after sync.

---

## 2. Production server access

```bash
ssh root@91.107.188.229
cd /opt/worldcup-predictor
git status -sb
git rev-parse HEAD
git rev-parse origin/main
ls -lh data/football_intelligence.db
du -h data/football_intelligence.db
systemctl status worldcup-api --no-pager
systemctl status nginx --no-pager
```

**Expected:**
- SSH succeeds
- Production DB exists (~9.5 GB)
- `worldcup-api` and `nginx` active
- Git dirty tree = runtime artifacts only (not source drift)

---

## 3. Version check

```bash
.venv/bin/python scripts/show_project_version.py || true
curl -s http://127.0.0.1:8000/api/version || true
```

**Expected:** JSON with `app_version`, `git_short`, `commit`; API `/api/version` returns 200 on production.

---

## 4. Pipeline dry-run (production)

```bash
.venv/bin/python scripts/run_production_prediction_pipeline.py --mode daily --dry-run
```

**Expected:** Exit 0; `dry_run: true`; stored prediction count unchanged.

---

## 5. Read-only prediction inspection

```bash
.venv/bin/python scripts/show_owner_predictions.py --date today --scope all --format table
```

**Expected:** Table of stored predictions or `NO_STORED_PREDICTIONS_FOUND` (not a crash).

---

## Report template

| Check | Result |
|-------|--------|
| GitHub access | yes / no |
| Hetzner SSH access | yes / no |
| Local commit | `<hash>` |
| GitHub commit | `<hash>` |
| Production commit | `<hash>` |
| Production DB visible | yes / no |
| Production service active | yes / no |
| Pipeline dry-run works | yes / no |
| Can run real predictions using production data | yes / no (requires owner approval for writes) |
| Missing access | `<list gaps>` |

---

## Hard rules for Claude

- **Never** copy production DB to local or GitHub
- **Never** commit `.env`, `*.db`, CSV dumps, shadow JSONL, secrets
- **Never** `rm data/football_intelligence.db` on production
- **Never** print `.env` or API keys in reports
- Code flow: **local → GitHub → Hetzner** (`git pull --ff-only`), not direct server edits
- Real production pipeline runs require **explicit owner approval**

---

*See `CLAUDE_PRODUCTION_RUNBOOK.md` for full operational commands.*
