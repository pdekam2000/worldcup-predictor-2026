# Hetzner SSH Setup — Phase 1 Scaffold (Local Preparation)

This guide prepares **secure SSH access** for the World Cup Predictor production server on Hetzner.

**Phase 1 scope:** local Windows key + config scaffolding and server bootstrap **proposal scripts only**.

**Phase 1 does NOT:**
- connect to Hetzner automatically
- create users on the server (unless an administrator manually runs the bootstrap script in a later approved step)
- modify `sshd_config`
- disable root login or password authentication
- deploy code or restart services

Production stack (confirmed): React frontend, FastAPI (`worldcup-api`), Nginx, uvicorn `:8000`, app root `/opt/worldcup-predictor`.

---

## A. Local Windows preparation

### Prerequisites

- Windows 10/11 with OpenSSH Client (`ssh`, `ssh-keygen`)
- Git repository checked out locally
- Administrator access to Hetzner (existing path — keep session open during testing)

### Generate key + SSH config (local only)

From the repository root in PowerShell:

```powershell
# Preview changes without writing files:
.\scripts\setup_hetzner_ssh_windows.ps1 -HostName YOUR_HETZNER_HOST -DryRun

# Apply (prompts for host if omitted):
.\scripts\setup_hetzner_ssh_windows.ps1 -HostName YOUR_HETZNER_HOST
```

The script will:

1. Verify `ssh` / `ssh-keygen` exist (prints install instructions if missing — does not silently install)
2. Create **ED25519** key at `%USERPROFILE%\.ssh\worldcup_hetzner_ed25519` **only if it does not exist**
3. **Never overwrite** an existing private key
4. Backup `%USERPROFILE%\.ssh\config` before changes
5. Add or update managed block:

```
Host worldcup-prod
    HostName <your-host>
    User deploy
    IdentityFile ~/.ssh/worldcup_hetzner_ed25519
    ...
```

6. Print the **public key** for server installation

**Never commit** private keys or passwords to the repository.

---

## B. One-time administrator bootstrap (server)

> **Do not run until you have reviewed** `scripts/bootstrap_hetzner_deploy_user.sh` and `deployment/sudoers/worldcup-deploy`.

Using your **existing administrative SSH session** (e.g. root):

```bash
# On server — PROPOSAL script (Phase 1)
export DEPLOY_PUBLIC_KEY='ssh-ed25519 AAAA... your-comment'
bash /opt/worldcup-predictor/scripts/bootstrap_hetzner_deploy_user.sh

# Or:
bash scripts/bootstrap_hetzner_deploy_user.sh --public-key-file /path/to/worldcup_hetzner_ed25519.pub
```

The bootstrap script:

- Requires **root**
- Creates `deploy` user only if missing (preserves existing user)
- Sets `~/.ssh` = `700`, `authorized_keys` = `600`
- Appends public key **only if not already present**
- Does **not** modify `sshd_config`
- Does **not** disable root login or password authentication

---

## C. Public key installation

Copy the public key printed by the Windows script. Install via bootstrap (preferred) or manually:

```bash
mkdir -p /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
# append key to /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
```

---

## D. Testing deploy-user SSH access

**Safe order:**

1. Generate dedicated key on Windows.
2. Copy/read the public key.
3. Log in using **existing** administrative access.
4. Run bootstrap (approved).
5. Install deploy public key.
6. Open a **NEW** terminal on Windows.
7. Test:

```powershell
ssh worldcup-prod
```

8. Confirm **key authentication** works.
9. Keep the existing admin session open until confirmed.

---

## E. Verifying restricted sudo (after manual sudoers install)

Review `deployment/sudoers/worldcup-deploy` on the server:

```bash
visudo -cf /etc/sudoers.d/worldcup-deploy   # after copying file to /etc/sudoers.d/
```

Approved wrappers (fixed service `worldcup-api`):

```bash
sudo /opt/worldcup-predictor/scripts/ops/worldcup_service_status.sh
sudo /opt/worldcup-predictor/scripts/ops/worldcup_service_restart.sh
sudo /opt/worldcup-predictor/scripts/ops/worldcup_logs.sh 100
```

Log wrapper rules:

- Default: 100 lines
- Maximum: 500 lines
- No arbitrary `journalctl` flags
- No arbitrary service name parameter

---

## F. Safe rollback / removal

### Windows

- Remove managed block from `%USERPROFILE%\.ssh\config` (between `BEGIN/END worldcup-prod` markers)
- Restore from `config.bak.*` if needed
- Delete keys only if you are certain they are unused: `worldcup_hetzner_ed25519` (+ `.pub`)

### Server

```bash
# Remove deploy authorized key line from /home/deploy/.ssh/authorized_keys
# Remove /etc/sudoers.d/worldcup-deploy if installed
visudo -c
```

Existing root/admin access remains until explicitly hardened in a **later approved phase**.

---

## G. Later SSH hardening (NOT Phase 1)

Only after `ssh worldcup-prod` works reliably:

- Consider `PasswordAuthentication no` (with confirmed key access)
- Consider restricting `PermitRootLogin`
- Consider fail2ban / allowlist
- Migrate operational scripts away from `root@<IP>` to `worldcup-prod`

**Never** lock out the existing admin path before key access is confirmed.

---

## Related files

| File | Purpose |
|------|---------|
| `scripts/setup_hetzner_ssh_windows.ps1` | Windows key + SSH config |
| `scripts/bootstrap_hetzner_deploy_user.sh` | Server bootstrap proposal |
| `deployment/sudoers/worldcup-deploy` | Restricted sudo proposal |
| `scripts/ops/worldcup_*.sh` | Approved command wrappers |
| `scripts/validate_phase1_ssh_scaffold.py` | Local validator |

---

## Validation (local)

```bash
python scripts/validate_phase1_ssh_scaffold.py
python -m pytest tests/test_phase1_ssh_scaffold.py -q
```

**No SSH connection is made by these commands.**
