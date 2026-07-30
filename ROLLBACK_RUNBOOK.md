# ROLLBACK RUNBOOK — Football Strength Shadow Infrastructure

## When to rollback

| Symptom | Action |
|---------|--------|
| Canonical λ / Exact / WDE values change unexpectedly | Immediate app rollback |
| API/GPT Actions down after deploy | Immediate app rollback |
| Shadow-only errors (form/totals/shadow rows) | Disable shadow hook if wired; **keep app**; leave tables |
| Migration concern | Prefer leave additive tables; drop only with owner approval |

## Preferred rollback (application only)

```bash
cd /opt/worldcup-predictor
export PRE_COMMIT=<sha-from-backup>/pre_commit.txt>
bash deployment/rollback_infrastructure.sh
```

Or explicitly:

```bash
APP=/opt/worldcup-predictor PRE_COMMIT=<PRE_DEPLOY_SHA> \
  bash deployment/rollback_infrastructure.sh
```

This will:

1. Check out the pre-deploy commit
2. Restart `worldcup-api` and `worldcup-gpt-actions`
3. Run health checks
4. Leave additive shadow tables in place (default)

## Table drop (optional, owner-approved only)

```bash
DROP_TABLES=1 PRE_COMMIT=<PRE_DEPLOY_SHA> bash deployment/rollback_infrastructure.sh
```

Drops only:

- `alternate_totals_capture_status`
- `totals_market_shadow_snapshots`
- `lambda_v2_shadow_outputs`
- `derived_historical_team_form_snapshots`

Does **not** touch `frozen_predictions`, results, or owner data.

## Restore DB from backup (emergency)

Only if sqlite corruption or accidental destructive change:

```bash
# example path written by run_infrastructure_deploy.sh
cp -a /opt/worldcup-predictor/backups/infra_deploy/<TS>/db/football_intelligence.db \
  /opt/worldcup-predictor/data/football_intelligence.db
sudo systemctl restart worldcup-api worldcup-gpt-actions
```

## Verify after rollback

- [ ] `systemctl is-active worldcup-api worldcup-gpt-actions`
- [ ] `curl -sf http://127.0.0.1:8000/api/health`
- [ ] `python deployment/canonical_regression_probe.py --mode local`
- [ ] Confirm no canonical freeze rows were rewritten

## Notes

- Additive migrations are forward-safe; rollback does **not** require dropping tables.
- Lambda V2 / Exact V2 were never canonical — rollback does not “un-promote” models.
