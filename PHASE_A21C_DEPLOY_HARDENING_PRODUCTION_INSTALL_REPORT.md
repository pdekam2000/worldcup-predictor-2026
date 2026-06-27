# Phase A21C — Deploy Hardening Production Install Report

**Date:** 2026-06-25  
**Server:** `91.107.188.229` · `/opt/worldcup-predictor`  
**Production URL:** https://footballpredictor.it.com  
**Final status:** `DEPLOY_HARDENING_PRODUCTION_READY`

---

## Executive summary

Phase A21B deploy hardening framework is installed on production. Detached deploys survive SSH disconnect via `systemd-run`, logs/status/checkpoints are written under `logs/deploy/`, and `python main.py deploy-status` is operational. **No application logic, schema, or frontend features were changed.** API remained **active** throughout (no downtime).

---

## Part 1 — Pre-upload backup

**Path:** `/opt/worldcup-predictor/backups/deploy-hardening-20260625_185845/`

| Item | Backed up |
|------|-----------|
| `scripts/deploy_phase_a19_production.sh` | Yes (if existed) |
| `scripts/deploy_phase_a20_quick.sh` | Yes |
| `scripts/deploy_phase_a21_quick.sh` | Yes |
| `main.py` | Yes |
| `pre_upload_commit.txt` | `ee762edc1a224c81fa0e87f5e713c47dc27ec823` |

---

## Part 2 — Uploaded files

| File | Purpose |
|------|---------|
| `scripts/lib/deploy_hardening.sh` | Lock, logs, resume, status JSON |
| `scripts/deploy_run.sh` | Detached launcher (`systemd-run` / `nohup`) |
| `scripts/validate_phase_a21b_deploy_hardening.py` | Validation |
| `scripts/deploy_phase_a19_production.sh` | Hardened A19 deploy |
| `scripts/deploy_phase_a20_quick.sh` | Hardened A20 deploy |
| `scripts/deploy_phase_a21_quick.sh` | Hardened A21 deploy |
| `scripts/deploy_hardening_noop_test.sh` | Safe no-op deploy test |
| `worldcup_predictor/ops/deploy_status.py` | deploy-status reader |
| `worldcup_predictor/ops/__init__.py` | ops package |
| `main.py` | Added `deploy-status` CLI |

**Not uploaded:** node_modules, frontend dist, database, cache, snapshots.

**Production fix applied during install:** Removed unsupported `systemd-run --pty=no` (systemd 259 on Ubuntu); scripts normalized to Unix LF (no CRLF/BOM).

---

## Part 3 — Install & permissions

```text
-rwxr-xr-x  scripts/deploy_run.sh
-rwxr-xr-x  scripts/lib/deploy_hardening.sh
-rwxr-xr-x  scripts/deploy_phase_a19_production.sh
-rwxr-xr-x  scripts/deploy_phase_a20_quick.sh
-rwxr-xr-x  scripts/deploy_phase_a21_quick.sh
-rwxr-xr-x  scripts/deploy_hardening_noop_test.sh
```

`deploy_hardening.sh` readable · `deploy_run.sh` executable · `logs/deploy/` created.

---

## Part 4 — Validation

```text
Phase A21B deploy hardening validation: 37/37 checks passed
```

Command:

```bash
cd /opt/worldcup-predictor
SKIP_FRONTEND_BUILD=1 .venv/bin/python scripts/validate_phase_a21b_deploy_hardening.py
```

---

## Part 5 — Safe detached deploy test

```bash
bash /opt/worldcup-predictor/scripts/deploy_hardening_noop_test.sh
```

**Result:**

```text
DEPLOY_LAUNCHED_OK session=20260625_190151_deploy_hardening_noop_test mode=systemd-run
unit=worldcup-deploy-20260625_190151
```

| Verify | Result |
|--------|--------|
| SSH returns immediately (detached) | PASS |
| Process survives after SSH exit | PASS (`state: ok`, `exit=0` in log) |
| Status file updates | PASS |
| Checkpoint updates | PASS (`noop_wait`, `noop_ok`) |
| Log file updates | PASS (1800 bytes) |

**systemd journal:**

```text
Started worldcup-deploy-20260625_190151.service - WorldCup Predictor deploy deploy_hardening_noop_test.
worldcup-deploy-20260625_190151.service: Deactivated successfully.
```

---

## Part 6 — Logging directory

**`/opt/worldcup-predictor/logs/deploy/`**

| Pattern | Present |
|---------|---------|
| `*.log` | Yes |
| `*.status.json` | Yes |
| `*.checkpoint` | Yes |
| `.latest_session` | Yes |
| `wrapper_*.log` | Yes |

---

## Part 7 — Rollback (verified, not executed)

Restore from backup:

```bash
BK=/opt/worldcup-predictor/backups/deploy-hardening-20260625_185845
cp -a "${BK}/main.py" /opt/worldcup-predictor/
cp -a "${BK}/scripts/"* /opt/worldcup-predictor/scripts/ 2>/dev/null || true
# Revert to commit in pre_upload_commit.txt if needed
```

No rollback performed.

---

## Part 8 — Production smoke

| Check | Result |
|-------|--------|
| `python main.py deploy-status` | PASS |
| Validation script | 37/37 PASS |
| Script permissions | PASS |
| Detached execution (`systemd-run`) | PASS |
| Journal output | PASS |
| `worldcup-api` active | PASS |
| `/api/health` | 200 |
| Application downtime | **None** |

---

## deploy-status output (latest session)

```text
Deploy session: 20260625_190151_deploy_hardening_noop_test
State: ok
Step: complete
Message: DEPLOY_OK
Log: /opt/worldcup-predictor/logs/deploy/deploy_20260625_190151_deploy_hardening_noop_test.log
Status file: .../deploy_20260625_190151_deploy_hardening_noop_test.status.json
Rollback: noop_test_no_app_changes backup=none
Checkpoint: noop_wait, noop_ok
```

---

## Usage (production)

```bash
# Detached deploy (survives SSH disconnect)
bash /opt/worldcup-predictor/scripts/deploy_phase_a21_quick.sh /tmp/your.tar.gz

# Monitor
python main.py deploy-status
python main.py deploy-status --json --log-lines 50
tail -f /opt/worldcup-predictor/logs/deploy/deploy_*.log
```

---

## What was NOT changed

WDE · EGIE · prediction models · scoring · calibration · billing · database schema · frontend features · backend business logic.

---

**Production status:** Deploy hardening framework is live and validated.

`DEPLOY_HARDENING_PRODUCTION_READY`
