# ECSE Evaluation Parity — Owner Report

**Recommendation:** `ECSE_PARITY_RESTORED_NO_RELIABILITY_SIGNAL`

---

## What happened

| | Before | After repair |
|---|-------:|-------------:|
| Local eligible ECSE evals | 16 | 16 |
| Production eligible ECSE evals | **1** | **16** |

Production was missing 14 frozen ECSE snapshots and 15 FT results that existed locally from controlled prediction work (Jun 29 – Jul 1). This was a **data sync gap**, not a broken evaluator.

---

## Root cause (one line)

**Historical ECSE snapshots and knockout results were generated/stored locally but never imported to Hetzner.**

---

## Per-fixture summary

| Fixture | Local | Prod (before) | Root Cause | Fixed? |
|---------|:-----:|:-------------:|------------|:------:|
| Brazil vs Japan | ✓ | ✗ | MISSING_PRODUCTION_ECSE | ✓ |
| Netherlands vs Morocco | ✓ | ✗ | MISSING_PRODUCTION_ECSE | ✓ |
| USA vs Bosnia | ✓ | ✗ | MISSING_PRODUCTION_ECSE | ✓ |
| Ivory Coast vs Norway | ✓ | ✗ | MISSING_PRODUCTION_ECSE | ✓ |
| Germany vs Paraguay | ✓ | ✗ | MISSING_PRODUCTION_ECSE | ✓ |
| France vs Sweden | ✓ | ✗ | MISSING_PRODUCTION_ECSE | ✓ |
| Australia vs Egypt | ✓ | ✗ | MISSING_PRODUCTION_ECSE | ✓ |
| Argentina vs Cape Verde | ✓ | ✗ | MISSING_PRODUCTION_ECSE | ✓ |
| Mexico vs Ecuador | ✓ | ✗ | MISSING_PRODUCTION_ECSE | ✓ |
| England vs Congo DR | ✓ | ✗ | MISSING_PRODUCTION_ECSE | ✓ |
| Belgium vs Senegal | ✓ | ✗ | MISSING_PRODUCTION_ECSE | ✓ |
| Portugal vs Croatia | ✓ | ✗ | MISSING_PRODUCTION_ECSE | ✓ |
| Colombia vs Ghana | ✓ | ✓ | OK (already on prod) | — |
| Spain vs Austria | ✓ | ✗ | MISSING_PRODUCTION_ECSE | ✓ |
| Switzerland vs Algeria | ✓ | ✗ | MISSING_PRODUCTION_ECSE | ✓ |
| Canada vs Morocco | ✓ | ✗ | MISSING_PRODUCTION_RESULT | ✓ |

---

## What we did (safe repair only)

- Imported **14 authentic ECSE snapshots** with original pre-kickoff timestamps
- Imported **15 fixture + result rows** from local canonical DB
- Updated Canada fixture status FT + result 0-3
- Ran ECSE evaluations on production (15 new eval rows)
- **Did not** regenerate predictions, change model logic, or overwrite Colombia's existing snapshot

Provenance: `artifacts/ecse_evaluation_parity_and_reliability_gate_1/parity_repair_export.json`

---

## Parity result

**16/16 intersection — full parity achieved.**

---

## Follow-up (optional, not done in this phase)

Deploy **result-truth schema v8** on Hetzner so AET matches (Belgium, Argentina) evaluate on regulation scores consistently with local.
