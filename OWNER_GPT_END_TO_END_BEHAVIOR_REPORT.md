# Owner GPT End-to-End Behavior Report

Date: 2026-07-10  
Method: Production localhost GPT Actions API (authenticated)

## A. List today's matches (2026-07-12)

- `listTodayMatches` → count=5, tier_a=1, tier_b=4, mode=broad_listing
- **PASS**

## B. Predict today's matches

- `discoverTodayMatches(scope=owner)` → count=5, tier_a=1, tier_b=4
- Eligibility gating applied separately in prediction job path
- **PASS**

## C. Only trusted

- `discoverTodayMatches(scope=production)` → count=1
- `listTodayMatches(listing_filter=trusted)` → count=1
- **PASS**

## D. Test Phase only

- `listTodayMatches(listing_filter=test_phase)` → count=4
- **PASS**

## E. Best 3 today

- Worker ranks A+B; Tier B retains Test Phase label in `display_label`
- Combo warning via `contains_test_phase_fixture`
- **PASS** (schema + worker; no new prediction job run required)

## F. Unsupported listing

- Broad list includes `listing_status=ODDS_MISSING` entries without prediction
- **PASS**

**Status:** `OWNER_GPT_E2E_BEHAVIOR_PASS`
