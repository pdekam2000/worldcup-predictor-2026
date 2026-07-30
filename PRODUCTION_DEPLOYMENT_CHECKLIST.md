# PRODUCTION DEPLOYMENT CHECKLIST

**Release:** `release/football-strength-shadow-infra-20260730T151432Z`  
**Commit:** `537266d`  
**Estimated duration:** 20–40 minutes (backup + migrate + restart + probes)

## Pre-deploy

- [ ] SSH access to production confirmed
- [ ] Confirm current production commit recorded
- [ ] Confirm free disk for DB backup
- [ ] Confirm `.env.production` present (do not print secrets)
- [ ] Confirm release commit reachable: `git fetch && git cat-file -e c8e68d7^{commit}`
- [ ] Note validated infra SHA `537266d` is ancestor of package tip `c8e68d7`
- [ ] Read `FINAL_DEPLOYMENT_AUDIT.md`
- [ ] Confirm no concurrent prediction backfills that lock FI DB
- [ ] Owner approval: infrastructure-only deploy (no model promotion)

## Deploy

```bash
cd /opt/worldcup-predictor
git fetch origin release/football-strength-shadow-infra-20260730T151432Z
# Optional baseline before checkout:
# .venv/bin/python deployment/canonical_regression_probe.py --mode before --baseline-dir /tmp/infra_baseline
sudo bash deployment/run_infrastructure_deploy.sh
```

Script stops on first failure (`set -euo pipefail`).

## Validation

- [ ] Healthcheck JSON status `PASS`
- [ ] Canonical regression `PASS` (λ identical with/without O/U 4.5)
- [ ] Shadow probe `PASS` and `canonical_blocked=false`
- [ ] Tables exist: form snapshots, totals shadow, lambda_v2 shadow, alternate_totals_capture_status
- [ ] Journal secret scan clean
- [ ] Spot-check one live canonical prediction (WDE/BTTS/O/U/Exact/no_bet) unchanged vs pre-deploy freeze if fixture available
- [ ] GPT Actions public response shape unchanged
- [ ] Frontend / Match Center still loads

## Rollback

```bash
PRE_COMMIT=<from backups/infra_deploy/<TS>/pre_commit.txt> \
  bash deployment/rollback_infrastructure.sh
```

See `ROLLBACK_RUNBOOK.md`.

## Post-deploy monitoring (first 24h)

- [ ] Canonical job success rate unchanged
- [ ] Shadow stage failures (informational; must not fail canonical)
- [ ] Alternate totals PRESENT/MISSING/STALE rates (MISSING is normal)
- [ ] Disk growth of shadow tables
- [ ] No spike in provider 429s attributable to totals capture

## Expected outputs

| Artifact | Location |
|----------|----------|
| Backup + summary | `/opt/worldcup-predictor/backups/infra_deploy/<TS>/` |
| Healthcheck | `.../post_deploy_healthcheck.json` |
| Canonical regression | `.../canonical_regression_report.md` |
| Shadow probe | `.../shadow_probe_report.md` |

## Emergency actions

1. If canonical drift → immediate `rollback_infrastructure.sh`
2. If API down → rollback + check journalctl
3. If shadow errors only → leave deploy; disable any optional shadow hook; do not drop freezes
4. Never force-push or rewrite freeze history
