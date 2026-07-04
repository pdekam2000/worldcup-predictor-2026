# RESULT TRUTH REPAIR 1 — Schema Audit

Phase: **RESULT-TRUTH-REPAIR-1** | Generated: 2026-07-04 21:45:41 UTC

## Column semantics (before repair)

| Column | FT fixture | AET fixture | PEN fixture |
|--------|------------|-------------|-------------|
| `home_goals` / `away_goals` | Provider final at FT (= regulation) | **Provider final after ET** (NOT regulation) | Provider aggregate at end of ET (= regulation, usually) |
| `final_score` | Same as legacy goals | Post-AET aggregate | Usually regulation draw score |
| `match_outcome_type` | FT | AET | PEN |
| `penalty_score` | null | null | Shootout score string |

## Provider field mapping (API-Football)

| Provider field | Meaning |
|----------------|---------|
| `score.fulltime` | **Regulation 90-minute score** |
| `goals.home/away` | Final aggregate (after ET if AET) |
| `score.extratime` | Goals scored in ET period only |
| `score.penalty` | Penalty shootout score |

## Evaluation consumers (pre-repair)

- `FixtureOutcomeResolver` — read `home_goals`/`away_goals` directly → **wrong for AET**
- `ecse_rerank.features.result_context` — assumed DB goals = 90m when AET flag set → **wrong**
- `pick_evaluator` / WDE eval — via FixtureOutcomeResolver → **wrong for AET**
- Owner tracker markdown — **manual** values, not DB canonical selection

## Answers

1. **FT `home_goals`:** regulation / final FT score.
2. **AET `home_goals` (legacy):** post-extra-time aggregate, not regulation.
3. **PEN `home_goals` (legacy):** score at end of ET (typically regulation draw).
4. **Regulation score provider field:** `score.fulltime`.
5. **Post-AET score:** `goals.home/away` when status=AET.
6. **Penalties:** `score.penalty`.
7. **Ambiguous consumers:** FixtureOutcomeResolver, result_context, manual owner tracker.

## Repair model

New explicit columns on `fixture_results`:
`regulation_home_goals`, `regulation_away_goals`, `extra_time_home_goals`, `extra_time_away_goals`,
`penalties_home_goals`, `penalties_away_goals`, `final_stage`, `qualified_team`, `result_synced_at`.

Legacy `home_goals`/`away_goals` **unchanged** for backward compatibility.
All standard market evaluation uses **regulation** via `market_result_resolver`.
