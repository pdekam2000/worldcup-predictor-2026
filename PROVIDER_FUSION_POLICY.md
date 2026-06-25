# Provider Fusion Policy — Phase 46D

**Version:** `46d_api_football_primary_v1`  
**Scope:** World Cup Predictor production pipeline

---

## Priority Order

For all entity resolution:

1. **API-Football** (primary / authoritative for WC pipeline)
2. **Sportmonks** (enrichment + gap-fill)
3. **Cache** (SQLite / file cache — stale-while-revalidate)

---

## Entity Rules

### Fixture identity

| Step | Rule |
|------|------|
| Primary key | API-Football `fixture_id` |
| Sportmonks link | `sportmonks_fixture_enrichment.api_fixture_id` |
| Conflict | Never overwrite API-Football fixture row with Sportmonks-only data |

### Score

| Source | Use |
|--------|-----|
| API-Football FT score | Authoritative for evaluation |
| Sportmonks scores | Fill when API-Football missing; never overwrite persisted result |
| Cache | Read-only fallback |

Function: `pick_primary_score()` in `provider_fusion.py`

### Events

| Rule | Detail |
|------|--------|
| Merge key | `(event_type, minute, extra_minute, team, player)` normalized |
| Primary | API-Football events list |
| Gap-fill | Sportmonks events not present in primary set |
| Conflict | Primary wins; Sportmonks duplicate discarded |
| Persistence | `fixture_unified_events` after enrichment |

Function: `merge_event_layers()` in `provider_fusion.py`

### Player / lineup

| Rule | Detail |
|------|--------|
| Lineups | API-Football `fixtures/lineups` primary |
| Sidelined / injuries | API-Football injuries + Sportmonks sidelined merge (enrichment service existing rules) |
| Player intelligence | Derived from merged lineups + events; no overwrite of engine payloads |

Function: `pick_entity()` in `provider_fusion.py`

### Odds

| Rule | Detail |
|------|--------|
| Snapshots | SQLite odds snapshots + API-Football odds |
| Rapid prematch | Supplemental opening/last when snapshots sparse |
| Movement | `build_odds_movement_intelligence()` — does not override WDE weights |

---

## Fallback Chain

```
Request data
  → SQLite cache hit? → use cache (mark source=cache)
  → API-Football live/cache? → use (source=api-football)
  → Sportmonks enrichment row? → gap-fill (source=sportmonks)
  → else unavailable (no fake data)
```

---

## Conflict Handling

| Situation | Action |
|-----------|--------|
| Score mismatch AF vs SM | Keep API-Football; log fusion note |
| Event minute differs | Keep primary event; optional note in fusion_notes |
| xG only on Sportmonks | Use for AdvancedMatchIntelligence; internal model unchanged |
| Odds disagree | Market consensus agents handle; movement intel informational |

---

## Non-Goals (46D)

- Do **not** override WDE factor weights
- Do **not** mutate stored predictions
- Do **not** synthesize placeholder provider data
- Do **not** replace API-Football as schedule/results authority

---

## Implementation

| Module | Role |
|--------|------|
| `provider_fusion.py` | Merge helpers |
| `unified_event_layer.py` | Event normalization + merge |
| `apply.py` | Orchestrates bundle on enrichment |
| `enrichment_service.py` | Calls `apply_provider_utilization` post-Sportmonks |

**Status:** PRODUCTION policy active with Phase 46D deploy.
