# Pre-Kickoff Odds Acceptance Fixture Selection

Generated: 2026-07-12 (Europe/Vienna)  
Source: production `discover_upcoming(days_ahead=2)` + owner scope filters

Excluded post-kickoff acceptance fixtures: 1581037, 1494694, 1495730, 1494206, 1494692.

## Selected fixtures

### Tier A Production — 1554381 (candidate; odds coverage pending)

| Field | Value |
|-------|-------|
| fixture_id | 1554381 |
| match | KuPS vs Vardar Skopje |
| competition | champions_league |
| tier | A |
| prediction_scope | production |
| kickoff_utc | 2026-07-14T15:00:00 |
| kickoff_vienna | 2026-07-14 17:00 CEST |
| hours_to_kickoff | ~63 |
| initial odds status | **No canonical 1X2 snapshot in DB** at selection time |

### Tier B Owner Shadow — 1494204 (primary positive-path fixture)

| Field | Value |
|-------|-------|
| fixture_id | 1494204 |
| match | Hammarby FF vs Kalmar FF |
| competition | allsvenskan |
| tier | B |
| prediction_scope | owner_shadow |
| kickoff_utc | 2026-07-12T12:00:00 |
| kickoff_vienna | 2026-07-12 14:00 CEST |
| hours_to_kickoff | ~12 |
| initial odds status | ODDS_STALE (provider=live, bookmaker_count=14, age ~943 min) |

### Tier B Owner Shadow — 1494205 (secondary)

| Field | Value |
|-------|-------|
| fixture_id | 1494205 |
| match | Malmo FF vs IFK Goteborg |
| competition | allsvenskan |
| tier | B |
| prediction_scope | owner_shadow |
| kickoff_utc | 2026-07-12T12:00:00 |
| kickoff_vienna | 2026-07-12 14:00 CEST |
| hours_to_kickoff | ~12 |
| initial odds status | Expected similar to 1494204 (same kickoff window) |

## Negative-path control

| fixture_id | match | reason |
|------------|-------|--------|
| 1581037 | Norway vs England | Post-kickoff; legitimate STALE_ODDS_AFTER_REFRESH block |

## Notes

- 27 upcoming owner-scope fixtures found within 48h.
- Primary positive-path proof uses **1494204** (pre-kickoff, stale→refresh→fresh→prediction OK).
- Tier A fixture 1554381 retained for scope coverage documentation; provider odds not yet persisted for CL qualifier at test time.
