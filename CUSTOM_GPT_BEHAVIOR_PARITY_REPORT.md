# Custom GPT Behavior Parity Report

Date: 2026-07-10

## Instructions vs deployed API

| Owner intent | Required flow | Parity |
|--------------|---------------|--------|
| List today's matches | `listTodayMatches` broad listing | PASS — `mode=broad_listing` |
| Predict today's matches | `discoverTodayMatches(scope=owner)` + job | PASS — owner returns A+B |
| Only trusted | `listing_filter=trusted` or `scope=production` | PASS — trusted count=1 |
| Test Phase only | `listing_filter=test_phase` or `scope=shadow` | PASS — test_phase count=4 |
| Best 3 today | A+B completed jobs, labels preserved | PASS — worker `contains_test_phase_fixture` |
| Unsupported listing | list without fake prediction | PASS — `listing_status` classifies, no auto-predict |

## Labels (production sample 2026-07-12)

- Tier A: `display_status=TRUSTED`, `display_label=TRUSTED`
- Tier B: `display_status=TEST_PHASE`, `display_label=TEST PHASE — UNDER FORWARD EVALUATION`

## OpenAPI

Version **1.1.0** documents `listTodayMatches`, tier metadata, combo warning fields.

**Status:** `CUSTOM_GPT_INSTRUCTION_PARITY_PASS`
