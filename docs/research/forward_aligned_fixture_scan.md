# Forward Aligned Fixture Scan

Research-only multi-day scanner that finds owner Tier A/B fixtures over the next 3–6 Vienna calendar days where WDE, ECSE direction, market, and quality signals align.

## Status

Research workflow. **Not** a production promotion of the WDE+ECSE agreement filter (forensic n=71 remains preliminary).

## Constraints

- Uses `CANONICAL_RESEARCH_EPHEMERAL` only.
- Zero canonical WSP / ECSE snapshot / freeze / evaluation writes during scan.
- Does not modify WDE or ECSE formulas.
- Does not auto-create official freezes.
- Public API / GPT Actions unchanged.

## Commands

```bash
python scripts/run_forward_aligned_fixture_scan.py --from-date 2026-07-21 --days 6 --scope owner
python scripts/validate_forward_aligned_fixture_scan.py --scan-id <SCAN_ID>
python scripts/report_forward_aligned_fixture_scan.py --scan-id <SCAN_ID>
python scripts/evaluate_forward_aligned_fixture_scan.py --scan-id <SCAN_ID>
```

Official freeze (owner-approved, never automatic):

```bash
python scripts/freeze_selected_aligned_fixtures.py --scan-id <SCAN_ID> --tier S --owner-approved
# then to execute:
python scripts/freeze_selected_aligned_fixtures.py --scan-id <SCAN_ID> --tier S --owner-approved --execute
```

## Alignment tiers

| Tier | Meaning |
|------|---------|
| S FULL_ALIGNMENT | WDE=FT=Top1=Top3maj=Top5maj, market ok, HIGH_AGREEMENT, no_bet=false, Top5 Mass≥0.52 |
| A STRONG_ALIGNMENT | WDE=Top5 maj + ≥2 supporting signals + HIGH_AGREEMENT; no_bet=true → CAUTION |
| B DIRECTIONAL | WDE=Top5 maj watchlist only |
| REJECTED | conflict / tie / stale odds / started / quality failure |

## Score

See `alignment.SCORE_FORMULA` — research-only 0–100 score; does not alter canonical outputs.

## Promotion gate

Do not promote until ≥200 confirmed finished fixtures, meaningful coverage, statistically supported lift, separate promotion review, and explicit owner approval.

## Artifacts

`artifacts/research/forward_aligned_fixture_scan/<SCAN_ID>/`

Reports: `reports/research/forward_aligned_fixture_scan_<DATE>.md`
