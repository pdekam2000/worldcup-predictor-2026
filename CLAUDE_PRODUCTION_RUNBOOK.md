# Claude Production Runbook — WorldCup Predictor

**Phase:** CLAUDE-OPS-1  
**Production path:** `/opt/worldcup-predictor`  
**Production DB:** `data/football_intelligence.db` (read-only for inspection; never copy/commit)

---

## 1. Check latest version

```bash
cd /opt/worldcup-predictor
git status -sb
git rev-parse HEAD
git rev-parse origin/main
.venv/bin/python scripts/show_project_version.py || true
curl -s http://127.0.0.1:8000/api/version || true
curl -s http://127.0.0.1:8000/api/health || true
```

All three environments (local PC, GitHub `main`, Hetzner) should share the same commit after deploy.

---

## 2. Check production DB exists

```bash
cd /opt/worldcup-predictor
ls -lh data/football_intelligence.db
du -h data/football_intelligence.db
.venv/bin/python -c "from worldcup_predictor.database.connection import is_connected; print('db_ok', is_connected())"
```

**Never** copy this file off the server. **Never** replace it with a local DB.

---

## 3. Pipeline dry-run (safe, no writes)

```bash
cd /opt/worldcup-predictor
.venv/bin/python scripts/run_production_prediction_pipeline.py --mode daily --dry-run
```

Dry-run sets `no_provider_calls` / dry flags — no DB mutation.

---

## 4. List stored predictions (read-only)

```bash
cd /opt/worldcup-predictor
.venv/bin/python scripts/show_owner_predictions.py --date today --scope all --format markdown
.venv/bin/python scripts/show_owner_predictions.py --date yesterday --scope evaluated --format table
.venv/bin/python scripts/show_owner_predictions.py --date tomorrow --scope pending --format json
```

No provider calls. No prediction generation. No DB writes.

---

## 5. Controlled real pipeline (owner approval required)

```bash
cd /opt/worldcup-predictor
.venv/bin/python scripts/run_production_prediction_pipeline.py --mode predictions-only --date today
.venv/bin/python scripts/run_production_prediction_pipeline.py --mode results-only
.venv/bin/python scripts/run_production_prediction_pipeline.py --mode eval-only
```

**Do not run** without explicit owner approval. **Do not enable** systemd timers without approval.

---

## 6. Check evaluations and accuracy

```bash
cd /opt/worldcup-predictor
.venv/bin/python scripts/show_owner_predictions.py --date yesterday --scope evaluated --format markdown
.venv/bin/python scripts/validate_implement_1_production_pipeline.py || true
```

Admin API (requires Bearer token + admin role):

```bash
curl -s -H "Authorization: Bearer <token>" \
  "http://127.0.0.1:8000/api/admin/owner-predictions?date=yesterday&scope=evaluated"
```

---

## 7. Check logs

```bash
journalctl -u worldcup-api -n 100 --no-pager
journalctl -u worldcup-prediction-daily.service -n 100 --no-pager || true
journalctl -u worldcup-results-hourly.service -n 100 --no-pager || true
```

---

## 8. Deploy approved GitHub changes to production

```bash
cd /opt/worldcup-predictor
git fetch origin main
git status -sb
git log --oneline HEAD..origin/main
git pull --ff-only origin main
.venv/bin/python -m compileall worldcup_predictor scripts
.venv/bin/python scripts/validate_implement_1_production_pipeline.py || true
.venv/bin/python scripts/validate_claude_ops_1_access_and_prediction_inspection.py || true
systemctl restart worldcup-api
curl -s http://127.0.0.1:8000/api/health || true
curl -s http://127.0.0.1:8000/api/version || true
```

Flow: **GitHub → Hetzner only**. No direct server code edits except emergency hotfix with approval.

---

## 9. What Claude must NEVER do

| Forbidden action | Why |
|------------------|-----|
| `rm data/football_intelligence.db` | Destroys production truth |
| Copy local DB to production | Overwrites canonical data |
| `scp` production DB to local/GitHub | Leaks runtime data; violates policy |
| Commit `*.db`, `.env`, CSV dumps, shadow JSONL | Secrets / runtime data in git |
| `cat .env` / print API keys in reports | Credential exposure |
| `git reset --hard` on production without approval | Loses runtime artifacts / risk |
| Edit source on Hetzner without GitHub sync | Source drift |
| Enable systemd timers without approval | Unattended production writes |
| Change WDE scoring / prediction formulas | Requires explicit model-change phase |

---

## Quick reference

| Task | Command |
|------|---------|
| Version | `git rev-parse HEAD` + `scripts/show_project_version.py` |
| Today's predictions | `scripts/show_owner_predictions.py --date today --scope all --format markdown` |
| Dry-run pipeline | `scripts/run_production_prediction_pipeline.py --mode daily --dry-run` |
| Controlled predict | `scripts/run_production_prediction_pipeline.py --mode predictions-only --date today` |
| SSH | `ssh root@91.107.188.229` |

---

*Timers remain disabled until operator explicitly approves after IMPLEMENT-1 / CLAUDE-OPS review.*
