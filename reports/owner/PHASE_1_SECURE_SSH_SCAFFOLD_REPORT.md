# Phase 1 — Secure SSH Scaffold Report

**Date:** 2026-07-09  
**Phase:** PHASE-1-SSH-SCAFFOLD (local only)  
**Branch:** `infra/phase1-secure-ssh-scaffold`  
**Base SHA:** `df93d421bdd03da78b86c5575431699ed7762659`  
**Production touched:** **NO**  
**SSH connection attempted:** **NO**  
**Secrets created in repo:** **NO**

---

## Phase status

**COMPLETE** — local scaffolding, validation, and tests only. **STOP** before Phase 2.

---

## Remote / main synchronization (Step 0)

| Item | Result |
|------|--------|
| `git fetch origin` | Performed safely |
| `git reset --hard` | **Not run** |
| Local work preserved | **Yes** — dirty tree unchanged |
| Ahead / behind `origin/main` | **0 / 2** (local behind) |
| `git pull --ff-only` on main | **Skipped** — dirty working tree |
| Branch strategy | `infra/phase1-secure-ssh-scaffold` from local HEAD |

### Remote-main files (verified on `origin/main`)

| File | Local checkout | On `origin/main` |
|------|----------------|------------------|
| `.github/workflows/validate-strict-live-refresh.yml` | Missing | Yes |
| `scripts/rerun_today_7_strict_live_predictions_20260709.py` | Missing | Yes |
| `worldcup_predictor/odds/strict_live_refresh.py` | Missing | Yes |
| `worldcup_predictor/odds/freshness_refresh.py` | Present (older) | Yes |
| `scripts/validate_strict_live_odds_refresh_fix.py` | Missing | Yes |

**No replacement** of strict-live files was created in Phase 1.

---

## Files created

| Path | Purpose |
|------|---------|
| `scripts/setup_hetzner_ssh_windows.ps1` | Windows ED25519 key + SSH config scaffold |
| `scripts/bootstrap_hetzner_deploy_user.sh` | Server bootstrap proposal (not executed) |
| `deployment/sudoers/worldcup-deploy` | Restricted sudoers proposal |
| `scripts/ops/worldcup_service_status.sh` | Fixed `worldcup-api` status wrapper |
| `scripts/ops/worldcup_service_restart.sh` | Fixed `worldcup-api` restart + verify |
| `scripts/ops/worldcup_logs.sh` | Bounded `journalctl` wrapper (max 500 lines) |
| `scripts/lib/phase1_ssh_scaffold.py` | Testable pure helpers |
| `scripts/validate_phase1_ssh_scaffold.py` | Local static validator |
| `tests/test_phase1_ssh_scaffold.py` | Unit tests |
| `docs/HETZNER_SSH_SETUP.md` | Operator documentation |
| `reports/owner/PHASE_1_SECURE_SSH_SCAFFOLD_REPORT.md` | This report |
| `artifacts/phase1_ssh_scaffold_validation.json` | Validator JSON output (generated) |

## Files modified

| Path | Change |
|------|--------|
| `reports/owner/INFRA_MCP_SSH_AUDIT.md` | Added **Remote/Main Drift Correction** section |

**Not modified:** WDE, ECSE, EGIE, odds freshness thresholds, providers, nginx, systemd production units, `.env.production`, prediction pipelines.

---

## Windows SSH script behavior

- Checks `ssh` / `ssh-keygen` availability; prints install guidance if missing
- Key: `%USERPROFILE%\.ssh\worldcup_hetzner_ed25519` (ED25519)
- **Never overwrites** existing private key
- HostName via `-HostName` parameter or interactive prompt — **no hardcoded IP in repo**
- SSH config backup before write (`config.bak.<timestamp>`)
- Idempotent managed block (`BEGIN/END worldcup-prod`)
- `-DryRun` supported
- **Does not** auto-connect

---

## Deploy bootstrap behavior (proposal)

- Requires root
- Creates `deploy` user only if missing
- `~/.ssh` permissions 700, `authorized_keys` 600
- Public key via `DEPLOY_PUBLIC_KEY` or `--public-key-file`
- Idempotent key append
- **Does not** modify `sshd_config`, root login, or password authentication

---

## Sudoers security model

- **No** `NOPASSWD: ALL`
- **No** `systemctl restart *` / `journalctl *`
- **No** shell/su/sudo -i grants
- Scoped `worldcup-api` systemctl commands (full paths — verify on server)
- Journalctl access **only** via `scripts/ops/worldcup_logs.sh`

---

## Validator results

Run: `python scripts/validate_phase1_ssh_scaffold.py`

Expected: `"all_passed": true` — see `artifacts/phase1_ssh_scaffold_validation.json`

---

## Test results

Run: `python -m pytest tests/test_phase1_ssh_scaffold.py -q`

Covers: SSH config idempotency, authorized_keys dedup, log line limits, sudoers comment stripping, secret scan.

---

## Remaining manual steps

1. Review PR (do not auto-merge).
2. Merge/rebase `origin/main` into feature branch when ready (brings strict-live workflow + scripts).
3. On Windows: `.\scripts\setup_hetzner_ssh_windows.ps1 -HostName YOUR_HOST`
4. On server (admin, later): run `bootstrap_hetzner_deploy_user.sh` with public key.
5. Install sudoers file after `visudo -c` review.
6. Test `ssh worldcup-prod` in a **new** terminal while keeping admin session open.

---

## Rollback / removal

- Windows: restore `~/.ssh\config` from `.bak.*`; remove managed block
- Server: remove deploy `authorized_keys` line; remove `/etc/sudoers.d/worldcup-deploy` if installed

---

## Recommendation for Phase 2

After PR merge path is agreed:

1. Sync local branch with `origin/main` (ff-only or merge commit — preserve dirty work on separate branch).
2. Add `.github/workflows/deploy-production.yml` (`workflow_dispatch` only).
3. Implement `scripts/production_{preflight,deploy_safe,rollback,health_check}.sh` by **extending** `run_codebase_consolidation_2_production_deploy.sh` patterns — not replacing phase deploy scripts.

---

*Phase 1 complete. No Hetzner connection. No bootstrap execution.*
