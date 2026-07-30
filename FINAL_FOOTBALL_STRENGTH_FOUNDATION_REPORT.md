# Football strength foundation

1. Canonical λ is odds-only via extract_lambdas (intentional market inversion path; football never connected).
2. Incomplete integration — not an intentional “no form forever” product decision.
3. team_form_snapshots empty because schema exists without writer/scheduler/ECSE hook.
4. O/U 3.5/4.5: training CSV partial; staging missing over-3.5/4.5; freezes do not store lines; eval cohort post-dates CSV (0 joins without inventing).
5. Football feature coverage: complete_feature 163/168 after identity+history service.
6. Feature freshness: kickoff-strict history only.
7. Leakage protections: validate_history_row assertions.
8. Best football-only: L2-A (Top5 46.4%, high Top5 0%).
9. Best market-total: L2-B/B0 (no alternate lines on cohort).
10. Best blended: L2-F (Top5 45.8%, high Top5 6.5%).
11–15. See executive summary table.
16–18. Exact V2 factorial + shadow 1176 rows.
19. Infra review-ready (additive).
20. Lambda/Exact V2 remain shadow.
21. Need ≥250 global, ≥40 actual 5+, ≥100 multi-line.
22–24. GitHub/prod/GPT Actions parity UNKNOWN until infra PR; no canonical schema change required for research tables.
25. Blockers: sample + totals coverage.

Status: FOOTBALL_STRENGTH_FOUNDATION_COMPLETE_LAMBDA_V2_PARTIAL
