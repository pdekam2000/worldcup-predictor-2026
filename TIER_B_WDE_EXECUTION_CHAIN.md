# Tier B WDE Execution Chain

## Call Path

```
startPredictionJob (GPT Actions REST)
  → worker.execute_prediction_job()
      → bootstrap_gpt_actions_runtime()  [FIX: added]
      → mcp_runtime.run_fixture_prediction()
          → bootstrap_gpt_actions_runtime()  [FIX: added]
          → ensure_fresh_odds_before_prediction()
          → run_daily_wde()
              → prepare_daily_fixture_for_wde()
                  → normalize_competition_key()
                  → register_tier_b_competition_runtime() [Tier B only]
              → settings.api_football_configured gate
              → PredictPipeline.run()
                  → DataCollectorAgent (SmartPredictionFetcher)
                  → SpecialistOrchestrator
                  → PredictionAgent
              → build_api_payload()
              → repo.upsert_worldcup_stored_prediction()
          → run_daily_ecse()
              → build_ecse_live_prediction()  [independent of API key gate]
          → _format_prediction_result()
              → extract_wde_semantics() → WDE / BTTS / O-U
```

## Tier B Routing

| Step | Module | Behavior |
|---|---|---|
| Discovery | `broad_fixture_discovery.py` | Tier B via `tier_b_shadow_registry` |
| Odds filter | `owner_odds.py` | Tier B controlled lookup |
| Prediction scope | `worker.py` | Tier B → `owner_shadow` |
| WDE prep | `wde_runtime.py` | Registers competition in `COMPETITION_REGISTRY` + SQLite |
| Shadow freeze | `shadow_storage.py` | Tier B only, non-public |

## Failure Injection Point (pre-fix)

`owner_daily/predictions.py:run_daily_wde()` line checking `settings.api_football_configured` before pipeline invocation when `API_FOOTBALL_KEY` not loaded from environment.

## ECSE Independence

ECSE builder reads fixture row + odds lambda inputs from SQLite. It does not pass through the API credentials gate that blocked WDE.
