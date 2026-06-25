# Phase 45B — Legacy Prediction Inventory

Generated from workspace inventory scan.

| Source | Count | Payload | Timestamp | Finished result | Safe import | User-private | Notes |
|--------|------:|---------|-----------|-----------------|-------------|--------------|-------|
| worldcup_stored_predictions (SQLite) | 2 | yes | yes | partial | no | no | Current global archive (Phase 33+). Authoritative production store. |
| predictions (legacy SQLite) | 17 | yes | yes | partial | no | yes | Legacy table — may overlap user-scoped rows; admin inventory only unless deduped. |
| prediction_history.jsonl | 0 | no | no | partial | no | yes | User/history JSONL — not for public performance import. |
| prediction_verification.jsonl | 542 | yes | yes | partial | no | no | Verification audit trail — not authoritative for public accuracy. |
| .cache/predictions/ | 4 | yes | yes | partial | no | yes | Per-fixture cache files — may duplicate stored predictions. |

## Recommendation

- Do **not** import legacy/cache rows into public performance metrics.
- Global archive (`worldcup_stored_predictions`) is the authoritative count for platform predictions.
- Legacy sources remain visible in admin diagnostics only.
