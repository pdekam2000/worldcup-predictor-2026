# Tier B WDE Dependency Matrix

| Dependency | Mandatory | Source | ECSE uses? | Tier A path | Tier B path | Five-fixture status (prod env) |
|---|---|---|---|---|---|---|
| APP_ENV=production | Yes (runtime) | systemd / bootstrap | No | Same | Same | Missing in direct scripts; present after fix |
| API_FOOTBALL_KEY | Yes (WDE gate) | `.env.production` | No | Same | Same | Available when bootstrap runs |
| Canonical fixture row | Yes | `fixtures` table | Yes | Same | Same | Present |
| Competition normalization | Yes | `competition_normalize.py` | Yes | Same | Same | eliteserien / urvalsdeild OK |
| Tier B registry entry | Yes | `tier_b_shadow_registry.py` | No | N/A | WDE prep | Registered at runtime |
| Odds H/D/A snapshot | Yes | `odds_snapshots` / canonical bridge | Yes (lambda) | Same | Same | FRESH_ODDS |
| Team intelligence | Yes | PredictPipeline / cache | Partial | Same | Same | Available (pipeline success) |
| WDE model artifact | Yes | ScoringEngine via pipeline | No | Same | Same | Loaded |
| ECSE snapshot tables | Optional | `ecse_live` store | Yes | Same | Same | Present |
| API cache dir | Optional (live fetch) | `data/cache/api_football` | No | Same | Same | Writable via bootstrap |

## Failure Behavior

| Missing dependency | Pre-fix code | Post-fix code | WDE status | ECSE status |
|---|---|---|---|---|
| API credentials | WDE_DEPENDENCY_FAILED | WDE_API_CREDENTIALS_MISSING | blocked_missing_dependency | unaffected |
| Stale odds (strict) | strict_fresh_odds_blocked | WDE_ODDS_STALE | blocked_missing_dependency | may skip |
| Team data | missing_team_data | WDE_TEAM_DATA_MISSING | blocked_missing_dependency | unaffected |
| WDE payload (downstream) | wde_payload_missing | unchanged | partial job | BTTS/O-U skipped_wde_payload_missing |
