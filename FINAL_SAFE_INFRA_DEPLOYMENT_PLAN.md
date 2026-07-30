# Safe infra deployment plan

## May deploy after review (additive)
- historical match query service
- derived form snapshot writer (or future-job production writer behind flag)
- totals market shadow persistence schema
- feature contract / metadata
- leakage tests

## Must NOT deploy as canonical yet
- Lambda V2
- Exact Score V2
- rank calibration
- regime selector

## Checklist
- [ ] migration review
- [ ] rollback scripts
- [ ] local/GitHub/prod/GPT Actions parity matrix
- [ ] no freeze mutation
- [ ] GPT Actions schema unchanged for canonical fields

Do not auto-deploy.
