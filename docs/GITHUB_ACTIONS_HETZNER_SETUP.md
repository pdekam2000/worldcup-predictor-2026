# GitHub Actions — Hetzner production deploy setup

This document describes how to configure **repository secrets** for the manual `Deploy production` workflow. **Do not commit secret values.**

## Required secrets

| Secret | Description |
|--------|-------------|
| `HETZNER_HOST` | Production server hostname or IP (e.g. `footballpredictor.it.com` or the Hetzner public IP) |
| `HETZNER_USER` | SSH user — must be **`deploy`** (not `root`) |
| `HETZNER_PORT` | SSH port (typically `22`) |
| `HETZNER_SSH_KEY` | Private key for the `deploy` user (ED25519 recommended) |
| `HETZNER_KNOWN_HOSTS` | Full `known_hosts` line(s) for the server |

## Create secrets (GitHub UI)

1. Repository → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** for each name above
3. Never paste secrets into workflow files, logs, or commits

## SSH key generation (admin workstation)

```powershell
# Windows — or use scripts/setup_hetzner_ssh_windows.ps1
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\worldcup_hetzner_ed25519 -C "github-actions-deploy"
```

- Store the **private** key in `HETZNER_SSH_KEY`
- Install the **public** key on the server for user `deploy` (see `scripts/bootstrap_hetzner_deploy_user.sh`)

**Never log or display `HETZNER_SSH_KEY`.**

## Known hosts (host verification)

From a **trusted administrator environment** (not CI), after verifying the server fingerprint out-of-band:

```bash
ssh-keyscan -p 22 YOUR_HOST 2>/dev/null
```

1. Compare the fingerprint with Hetzner console / prior trusted record
2. Copy the full line into `HETZNER_KNOWN_HOSTS`

**Do not use `StrictHostKeyChecking=no`.** The workflow writes `HETZNER_KNOWN_HOSTS` to `~/.ssh/known_hosts` with mode `600`.

## Deploy user and sudoers

1. Bootstrap `deploy` user: `scripts/bootstrap_hetzner_deploy_user.sh` (manual, admin only)
2. Install restricted sudoers: `deployment/sudoers/worldcup-deploy` → `/etc/sudoers.d/worldcup-deploy`
3. Validate: `visudo -cf /etc/sudoers.d/worldcup-deploy`

Allowed remote commands (fixed paths):

- `scripts/production_preflight.sh`
- `scripts/production_deploy_safe.sh`
- `scripts/production_health_check.sh`
- `scripts/production_rollback.sh`
- Phase 1 ops wrappers (`scripts/ops/worldcup_service_*.sh`)

## GitHub Environment (recommended)

Protect the `production` environment with required reviewers before the deploy job runs.

## Manual deploy trigger

1. Merge approved changes to `main`
2. Actions → **Deploy production (manual)** → **Run workflow**
3. Enter `target_sha` — must be a commit on `main` history
4. Review artifacts and logs (sanitized; no secrets)

## What this workflow does not do

- Does not create secrets automatically
- Does not run on every push to `main` (manual only)
- Does not retrain models or regenerate predictions
- Does not modify `.env.production`
- Does not replace the production database on code-only failure

## Rollback policy

- Code rollback uses `scripts/production_rollback.sh` with a recorded previous SHA
- **Database restore is not automatic** — set `RESTORE_DB=1` and `SQLITE_BACKUP_PATH` only when a migration requires it

## Related docs

- `docs/HETZNER_SSH_SETUP.md` — operator SSH scaffold (Phase 1)
- `deployment/CHECKLIST.md` — server bootstrap
- `deployment/ROLLBACK.md` — manual rollback reference
