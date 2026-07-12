# Provider Feature Usage Matrix

| Feature | Provider | Stored field | WDE | ECSE | BTTS | O/U | Confidence | Selection | Status |
|---------|----------|--------------|-----|------|------|-----|------------|-----------|--------|
| Odds consensus (1X2) | API-Football/OddAlerts | `odds_snapshots`, CSV odds | Yes | Yes | Implied | Implied | Via data quality | Yes | **Primary** |
| Implied probabilities | Derived | `implied_prob_*` | Yes | Lambda input | Yes | Yes | Yes | Yes | **Used** |
| Bookmaker count | Canonical snapshot | payload metadata | Indirect | No | No | No | Yes | No | Used |
| Market entropy | Derived | computed | No | No | No | No | Possible | No | Shadow tested |
| xG for/against (pre-match) | SportMonks | `xg_snapshots` | Shadow promo only | Research | No | No | Shadow | No | **Underused** (sparse) |
| xG (CSV realized) | External CSV | `expectedGoalsHome` | Diagnostic only | Diagnostic | No | No | No | No | **Leakage — not promotable** |
| Team form | API-Football | enrichment / intel report | Yes | No | No | No | Yes | No | Used |
| Home/away form split | API-Football | intel report | Yes | No | No | No | Yes | No | Used |
| Lineup strength | API-Football | enrichment lineups | Yes | No | No | No | Yes | No | Used when available |
| Injuries | API-Football | enrichment | Yes | No | No | No | Yes | No | Used |
| H2H | API-Football | enrichment | Yes | No | No | No | Partial | No | Used |
| Standings/motivation | API-Football/SportMonks | enrichment | Context | No | No | No | Partial | No | Partial |
| Pressure index | SportMonks | pressure store | No | No | No | No | No | No | **Unused in production** |
| Shots/possession | API-Football stats | enrichment (post-match) | No | No | No | No | No | No | **Post-match only** |
| OddAlerts segments | OddAlerts CSV | probability rows | No | Shadow | Shadow | Shadow | Shadow | Shadow | Shadow only |
| Provider prediction model | API-Football/SportMonks | cache | Reference | No | No | No | No | No | **Underused** |
| Weather | WeatherAPI | supplemental | Confidence | No | No | No | Yes | No | Supplemental |
| Opening vs closing odds | Multi | snapshot timestamps | Movement (if valid) | No | No | No | Possible | No | Needs timestamp audit |

## Priority recommendations

1. **High:** Canonical pre-match odds features (already primary; extend entropy/movement with valid timestamps)
2. **Medium:** SportMonks pre-match xG snapshots (coverage backfill required)
3. **Medium:** Lineup/injury snapshots with explicit `feature_available_at`
4. **Low:** Live pressure, post-match statistics for pre-match models
5. **Shadow only:** OddAlerts ECSE segments (continue shadow evaluation)
