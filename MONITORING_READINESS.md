# MONITORING READINESS

## Covered signals

| Signal | How to observe | Alert? |
|--------|----------------|--------|
| Shadow job success/failure | shadow orchestrator stage results / logs | Yes on hard exceptions rate |
| Form snapshot success/failure | `derived_historical_team_form_snapshots` insert rate + stage logs | Yes on sustained failure |
| Alternate totals PRESENT/MISSING/STALE | `alternate_totals_capture_status.status` | **No** for normal MISSING; Yes for unexpected exception storms |
| Provider failures | existing odds refresh / API football logs | Yes (existing canonical gates) |
| Database write failures | sqlite errors in shadow stages | Yes |
| Duplicate prevention | unique snapshot/status ids; reruns should not explode row counts | Informational |
| Disk growth | table sizes / DB file size daily | Yes if > projected monthly envelope |
| Latency | shadow orchestrator duration in probe/logs | Yes if p95 blocks workers (should be non-blocking) |
| Canonical job success | existing forward/daily prediction success | **Primary SLO — Yes** |

## Explicit non-alerts

- Missing O/U 3.5 or 4.5 lines → status `MISSING` is expected and must not page.
- Stale odds → status `STALE`; canonical freshness gates remain authoritative.

## Minimal SQL checks

```sql
SELECT status, COUNT(*) FROM alternate_totals_capture_status GROUP BY status;
SELECT COUNT(*) FROM derived_historical_team_form_snapshots;
SELECT COUNT(*) FROM lambda_v2_shadow_outputs;
```

## Log hygiene

- Never log API keys, JWT secrets, or full `.env`
- Deploy script scans recent journal output for obvious secret patterns

## Status

Monitoring **spec + checklist ready**. Wire to production dashboards after first successful deploy.
