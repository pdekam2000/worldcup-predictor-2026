# TSBP DOMAIN COVERAGE REPORT

Policy version: `tsbp-domain-v1`

```json
{
  "policy_version": "tsbp-domain-v1",
  "source": "phase3b_domain_breakdown",
  "min_league_history": 80,
  "min_team_games": 3,
  "classifications": {
    "premier_league": "TSBP_FORWARD_ENABLED",
    "bundesliga": "TSBP_FORWARD_ENABLED",
    "champions_league": "TSBP_RESEARCH_ONLY",
    "world_cup_2026": "TSBP_RESEARCH_ONLY"
  },
  "notes": [
    "Only premier_league and bundesliga had sufficient Phase 3B coverage with team-strength beating league baseline.",
    "champions_league / world_cup_2026 remain RESEARCH_ONLY (insufficient Challenger snapshot rows).",
    "Other Tier B leagues are UNSUPPORTED until Phase 3B-style evidence exists.",
    "Do not auto-enable every Tier B competition."
  ]
}
```

Forward enabled only where Phase 3B had sufficient coverage and team-strength beat league baseline:
- premier_league → TSBP_FORWARD_ENABLED
- bundesliga → TSBP_FORWARD_ENABLED
- champions_league / world_cup_2026 → TSBP_RESEARCH_ONLY
- other competitions → TSBP_UNSUPPORTED