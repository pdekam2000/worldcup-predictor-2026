# Phase 48A — Real Production Accuracy Monitoring Report

**Status:** PRODUCTION_ACTIVE  
**Date:** 2026-06-22 UTC

---

## Executive Summary

Phase 48A adds **real production accuracy monitoring** tied to settled SQLite evaluations — not replay estimates. Snapshots are captured automatically whenever the accuracy summary rebuilds (including the 30-minute auto-evaluation cycle).

Production can now answer, from live data:

- Is Rule A improving real 1X2 outcomes?
- Which markets perform best / worst?
- How does accuracy trend over 7 / 30 days?
- Which intelligence layers correlate with winning predictions?

---

## Part A — Performance Snapshots

**Table:** `performance_snapshots`

| Field | Purpose |
|-------|---------|
| `snapshot_at` | UTC timestamp |
| `evaluated_count` / `correct_count` / `wrong_count` / `pending_count` | Global counts |
| `overall_winrate` | 1X2 win rate at snapshot time |
| `markets_json` | Per-market winrate, sample_size, reliability |
| `rule_a_json` | Rule A impact counters |
| `agent_contribution_json` | Specialist layer tracking |

**Markets tracked:** 1X2, Over/Under 2.5, BTTS, Double Chance, HT Result, Correct Score, First Goal Team, Goalscorer, Goal Minute.

**Reliability levels:** Low (&lt;20), Medium (20–49), High (≥50).

**Capture trigger:** `rebuild_accuracy_summary()` → `capture_performance_snapshot()` (fail-silent).

---

## Part B — Rule A Impact Tracking

Counters on settled 1X2 evaluations with harmonization telemetry:

| Counter | Meaning |
|---------|---------|
| `wde_preserved` | Published 1X2 kept WDE (odds absent path) |
| `scoreline_override` | Scoreline harmonization applied |
| `beneficial_override` | Scoreline right, WDE would have been wrong |
| `harmful_override` | WDE right, scoreline override wrong |
| `neutral_override` | Both wrong on conflict |
| `override_rate` | scoreline_override / tracked decisions |

Telemetry read from stored prediction payloads: `harmonization_used`, `harmonization_reason`, `harmonization_source` (stamped at predict time since Phase 47C).

---

## Part C — Performance Center V2

**Endpoint:** `GET /api/performance/summary` (version `v2`)

New fields:

- `accuracy_trends` — 7d / 30d / all-time from snapshots
- `market_leaderboard` — ranked markets
- `rule_a_monitoring` — live Rule A counters
- `agent_contribution` — tracking-only specialist influence
- `snapshot_count`

**Additional route:** `GET /api/performance/monitoring`

**Frontend:** `/accuracy` — Accuracy Trend, Rule A Monitoring, Market Leaderboard sections.

---

## Part D — Market Leaderboard

Ranked by winrate then sample size. Includes reliability badge per market.

---

## Part E — Agent Contribution Tracking

Tracking-only (no WDE changes):

| Layer | Source |
|-------|--------|
| Weather | `weather_agent` |
| Odds Cluster | odds_market, consensus, sharp, control agents |
| Odds Movement | `odds_movement_agent` |
| Advanced Match Intelligence | `provider_utilization_v1` bundle |
| Player Intelligence | player intelligence bundle |
| Provider Fusion | provider utilization bundle |

Metrics: `recommendation_count`, `avg_influence_score`, `alignment_rate` with winning 1X2.

---

## Part F — Validation

**Script:** `scripts/validate_phase48a_real_accuracy_monitoring.py`  
**Result:** 19/19 PASS (local + production)

Verified: snapshots, calculations, Rule A telemetry, no fake data, WDE/scoring/archive unchanged.

---

## Part G — Production Deploy

| Step | Result |
|------|--------|
| Backup | `/opt/worldcup-predictor/backups/deploy-phase48a-20260622-030312` |
| Backend + frontend | Deployed |
| API restart | active |
| Validation | 19/19 PASS |
| Smoke | 5/5 PASS |

**Production at deploy:** 4 evaluated fixtures (growing as auto-evaluation runs).

---

## Success Criteria

| Question | Answerable? |
|----------|-------------|
| Is Rule A improving production accuracy? | Yes — via `rule_a_monitoring` + trends as samples grow |
| Best / worst market? | Yes — `market_leaderboard` |
| Specialist correlation with wins? | Yes — `agent_contribution` |
| Accuracy over time? | Yes — `accuracy_trends` + snapshots |

**Replay benchmark (Phase 47C):** 30.0% → 36.7% on n=207 offline. Production will confirm or refute as WC fixtures settle.

---

**PHASE_48A_STATUS = PRODUCTION_ACTIVE**
