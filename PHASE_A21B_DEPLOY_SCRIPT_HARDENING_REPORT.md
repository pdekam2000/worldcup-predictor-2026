# Phase A21B — Deploy Script Hardening Report

**Date:** 2026-06-25  
**Goal:** Prevent production deploy failures when SSH sessions drop during long-running scripts  
**Final status:** `DEPLOY_HARDENING_OK` · `IMPLEMENTED_NOT_DEPLOYED`

---

## Executive summary

Deploy infrastructure is now hardened with **detached execution**, **timestamped logs**, **resumable steps**, **exclusive locking**, and a **`deploy-status` CLI**. No product logic (WDE, models, scoring, billing) was changed. Scripts are ready on disk; **not pushed to production** in this phase.

---

## Problem addressed

Phase A19 production deploy failed with **SSH exit 255** after ~2 hours (`client_loop: send disconnect: Connection reset`). The deploy process was tied to the interactive SSH session and died when the connection dropped.

---

## Solution

### 1. Shared hardening library

**`scripts/lib/deploy_hardening.sh`**

| Feature | Implementation |
|---------|----------------|
| Timestamped logs | `deploy_log` → `${DEPLOY_LOG_DIR}/deploy_<session>.log` |
| Status file | JSON at `${DEPLOY_LOG_DIR}/deploy_<session>.status.json` |
| Resume | Checkpoint file — completed step names; `deploy_run_step` skips done steps |
| Lock | `flock` on `${DEPLOY_LOG_DIR}/.deploy.lock` blocks concurrent deploys |
| Rollback hint | Recorded in status JSON (`rollback` field) |

Default log directory: **`/opt/worldcup-predictor/logs/deploy/`**

### 2. Detached launcher

**`scripts/deploy_run.sh`**

- Usage: `deploy_run.sh [--foreground] [--resume SESSION] <script> [args...]`
- Prefers **`systemd-run`** (survives SSH disconnect, collected unit)
- Falls back to **`nohup`** when systemd-run unavailable
- Writes `.latest_session`, `.pid`, wrapper log
- Prints `DEPLOY_LAUNCHED_OK`, log path, and status path immediately

Production deploy scripts re-exec through this wrapper unless `WC_DEPLOY_CHILD=1` or `--foreground`.

### 3. Updated deploy scripts

| Script | Changes |
|--------|---------|
| `scripts/deploy_phase_a21_quick.sh` | Full step-based + hardening |
| `scripts/deploy_phase_a19_production.sh` | Full step-based + hardening |
| `scripts/deploy_phase_a20_quick.sh` | Full step-based + hardening |

Resumable steps (example A21): `backup` → `extract` → `migrate` → `frontend_build` → `restart_api` → `nginx` → `validate` → `smoke`

### 4. Deploy status CLI

```bash
python main.py deploy-status
python main.py deploy-status --session 20260625_120000_phase_a21
python main.py deploy-status --json --log-lines 50
```

Reads latest or specified session from `logs/deploy/`, shows state, step, rollback hint, lock info, and log tail.

**Module:** `worldcup_predictor/ops/deploy_status.py`

---

## Validation

**`scripts/validate_phase_a21b_deploy_hardening.py`** — **30/30 PASS**

| Check | Result |
|-------|--------|
| Hardening lib + deploy_run present | PASS |
| A19/A20/A21 scripts use wrapper + hardening | PASS |
| `main.py deploy-status` registered | PASS |
| Status file + log + checkpoint creation | PASS |
| Resume skips completed steps | PASS |
| Lock blocks duplicate deploy (flock) | PASS |
| systemd-run + nohup paths in wrapper | PASS |
| WDE unchanged | PASS |

Output: `data/validation/phase_a21b_deploy_hardening_validation.json`

---

## Usage (production, after deploy of these scripts)

```bash
# Launch detached (recommended — survives SSH drop)
bash /opt/worldcup-predictor/scripts/deploy_phase_a21_quick.sh /tmp/phase_deploy.tar.gz

# Monitor from any shell
python main.py deploy-status
tail -f /opt/worldcup-predictor/logs/deploy/deploy_*.log

# Resume after interruption (same session id)
DEPLOY_RESUME_SESSION=20260625_120000_phase_a21 \
  bash /opt/worldcup-predictor/scripts/deploy_run.sh --resume 20260625_120000_phase_a21 \
  /opt/worldcup-predictor/scripts/deploy_phase_a21_quick.sh /tmp/tarball.tar.gz

# Foreground debug (blocks SSH — dev only)
DEPLOY_FOREGROUND=1 bash /opt/worldcup-predictor/scripts/deploy_run.sh --foreground \
  /opt/worldcup-predictor/scripts/deploy_phase_a21_quick.sh /tmp/tarball.tar.gz
```

---

## Files added / changed

| Path | Action |
|------|--------|
| `scripts/lib/deploy_hardening.sh` | **Added** |
| `scripts/deploy_run.sh` | **Added** |
| `scripts/deploy_phase_a21_quick.sh` | Updated |
| `scripts/deploy_phase_a19_production.sh` | Updated |
| `scripts/deploy_phase_a20_quick.sh` | Updated |
| `worldcup_predictor/ops/deploy_status.py` | **Added** |
| `worldcup_predictor/ops/__init__.py` | **Added** |
| `main.py` | `deploy-status` command |
| `scripts/validate_phase_a21b_deploy_hardening.py` | **Added** |

---

## Rollback

Revert to pre-A21B deploy scripts from git. Hardening is additive — existing tarball/smoke flow unchanged; only execution wrapper and logging differ.

---

## Next step (not done in A21B)

Upload hardened scripts to production server and run one smoke deploy with `deploy-status` monitoring. Per phase scope: **IMPLEMENTED_NOT_DEPLOYED**.
