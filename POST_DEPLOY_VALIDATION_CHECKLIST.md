# Post-deploy validation checklist

- [ ] Canonical freeze job succeeds
- [ ] extract_lambdas outputs unchanged for fixture with only new 4.5 fields
- [ ] Shadow form rows written for new fixtures
- [ ] alternate_totals_capture_status has PRESENT or MISSING
- [ ] No freeze row UPDATEs from shadow path
- [ ] GPT Actions schema diff empty for canonical
- [ ] Rollback drill documented
