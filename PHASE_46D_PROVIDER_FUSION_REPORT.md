# Phase 46D — Provider Fusion Report

**Version:** `46d_api_football_primary_v1`  
**Status:** ACTIVE IN PRODUCTION  
**Date:** 2026-06-21

---

## Purpose

Define and implement a single fusion policy so API-Football and Sportmonks data merge predictably across fixtures, events, scores, players, lineups, and odds — without overwriting authoritative API-Football records or injecting synthetic data.

---

## Priority Stack

```
1. API-Football  (authoritative for WC pipeline)
2. Sportmonks    (enrichment + gap-fill)
3. Cache         (SQLite / file — stale-while-revalidate)
```

---

## Implementation

**Policy doc:** `PROVIDER_FUSION_POLICY.md`  
**Code:** `worldcup_predictor/intelligence/provider_utilization/provider_fusion.py`

| Function | Entity | Behavior |
|----------|--------|----------|
| `pick_entity()` | Generic | First non-empty value by priority list |
| `pick_primary_score()` | Score | API-Football FT authoritative; SM fills gaps only |
| `merge_event_layers()` | Events | Dedupe by normalized key; primary wins conflicts |
| `merge_event_layers()` | | SM events appended only when not in primary set |

---

## Event Merge Key

Normalized tuple:

```
(event_type, minute, extra_minute, team, player)
```

- API-Football events parsed first → `source=api-football`
- Sportmonks events scanned → added if key absent → `source=sportmonks`
- Cached events loaded before live merge when present

**Persistence:** Merged set written to `fixture_unified_events` on first enrichment (cache miss).

---

## Score Fusion

| Scenario | Resolution |
|----------|------------|
| Both providers have FT score | API-Football used for evaluation |
| API-Football missing, SM present | SM score as read-only fallback |
| Conflict (different FT) | API-Football wins; SM logged in fusion notes |
| Neither available | `unavailable` — no fake data |

---

## Lineup & Player Fusion

| Data | Primary | Secondary |
|------|---------|-----------|
| StartXI / formation | API-Football lineups | Sportmonks lineups (gap-fill) |
| Injuries | API-Football injuries | Sportmonks sidelined |
| Player intelligence | Derived from merged inputs | Never overwrites engine payloads |

---

## Odds Fusion

| Layer | Source |
|-------|--------|
| Snapshots | SQLite `odds_snapshots` (consensus over time) |
| Opening/last | RapidAPI prematch supplemental |
| Movement intel | `build_odds_movement_intelligence()` |

Odds movement intelligence **does not override WDE weights** — informational supplemental only.

---

## Runtime Application

Fusion executes inside `build_unified_event_layer()` and `apply_provider_utilization()` during enrichment:

```
enrichment_service
  → apply_sportmonks_consumption()
  → apply_provider_utilization()   ← fusion + bundles
```

Output attached to `MatchIntelligenceReport.supplemental_sources`.

---

## Conflict Handling Summary

| Conflict Type | Rule |
|---------------|------|
| Duplicate event (same key) | Keep API-Football copy |
| Score mismatch | API-Football authoritative |
| Missing primary field | Sportmonks gap-fill |
| Missing all sources | Return empty / unavailable |
| Stale cache | Re-enrich on next fixture intelligence build |

---

## Validation Evidence

Production validation confirms:

- Unified events parse and persist correctly
- Fusion does not alter WDE factor weights
- Core evaluators (1X2, goal minute) unchanged
- `apply_provider_utilization` produces all five bundle keys

---

## Operational Notes

- Fusion is **extend-only** — no existing tables overwritten except `fixture_unified_events` replace-by-fixture
- Sportmonks enrichment cache (`sportmonks_fixture_enrichment`) remains read path for raw fixture payload
- Circular import between odds modules resolved via lazy imports and local helpers (deploy fix 2026-06-21)

---

**Fusion policy: PRODUCTION_ACTIVE**
