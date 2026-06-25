# HOTFIX — WEATHER CONFIG MISMATCH ON PRODUCTION PREDICT PAYLOAD

**Date:** 2026-06-21  
**Status:** **DEPLOYED**  
**Backup:** `/opt/worldcup-predictor/backups/deploy-hotfix-weather-20260621-171204`

---

## Root cause

**Not a missing `WEATHER_API_KEY`.** Production env and systemd were configured correctly after Phase 43.

The mismatch was caused by **stale fields inside frozen SQLite prediction payloads**:

1. Fixture `1489393` was predicted and **frozen post-kickoff** on `2026-06-20T19:46:48Z` — **before** Phase 43 deployed weather intelligence (`2026-06-21`).
2. At generation time, `provider_readiness.weather_configured=false` and `weather_intelligence.available=false` were stamped into the stored payload.
3. `GET /api/predict/{id}` served the cached blob **without refreshing** `provider_readiness` from current runtime settings.
4. This made Phase 43 appear broken even though the live process had `weather_configured=True`.

Secondary issue: clients calling **`/api/predictions/{id}`** (typo) hit a non-existent route and could hang/time out instead of returning a fast helpful 404.

---

## Production environment verification

| Check | Result |
|-------|--------|
| `WEATHER_API_KEY` in `.env.production` | **Present** (value length 30, not printed) |
| `WEATHER_CACHE_TTL_SECONDS` in `.env.production` | **Present** (`3600`) |
| `WEATHER_PROVIDER` | **weatherapi** (default) |
| systemd `EnvironmentFile` | `/opt/worldcup-predictor/.env.production` |
| Running `worldcup-api` process has `WEATHER_API_KEY` | **Yes** (length 30) |
| Runtime `get_settings().weather_provider_configured` | **True** |
| Provider env var name | **`WEATHER_API_KEY`** — matches `settings.py` alias and `WeatherProvider` |

---

## Fix implemented

### 1. Refresh provider readiness on every predict response

`enrich_prediction_payload()` now calls `stamp_provider_readiness()` so cached payloads always reflect **current** env — not snapshot-time values.

### 2. Weather intelligence serve-time refresh

New `_refresh_weather_intelligence_on_serve()`:

| Cache state | Behavior |
|-------------|----------|
| **Frozen post-kickoff** | Does **not** backfill weather. Sets `unavailable_reason=frozen_post_kickoff_snapshot`, `provider_now_configured=true`, explanatory `note`. |
| **Live / stale non-frozen** | Lazy-fetches weather via `WeatherProvider` when city is valid. |
| **Provider not configured** | `unavailable_reason=provider_not_configured` |

### 3. Safe diagnostic endpoint

`GET /api/health/providers` — public, no secrets:

```json
{
  "status": "ok",
  "weather_configured": true,
  "weather_provider": "weatherapi",
  "weather_provider_ready": true,
  "weather_cache_ttl_seconds": 3600,
  "loaded_env_file": ".env.production",
  "app_env": "production"
}
```

### 4. Wrong endpoint guard

`GET|POST /api/predictions/{fixture_id}` → **404** with:

```json
{
  "code": "wrong_endpoint",
  "message": "Wrong path: use GET or POST /api/predict/{fixture_id} ...",
  "correct_path": "/api/predict/1489393"
}
```

---

## Validation results

### Local

```
python scripts/validate_hotfix_weather_config_mismatch.py
→ 13/13 PASS
```

### Production (post-deploy)

| Test | Result |
|------|--------|
| `GET /api/health/providers` | `weather_configured=true`, `weather_provider_ready=true` |
| `GET /api/predict/1489393` | `provider_readiness.weather_configured=true` |
| `GET /api/predict/1489393` weather block | `unavailable_reason=frozen_post_kickoff_snapshot`, `provider_now_configured=true` |
| `GET /api/predictions/1489393` | **404** in <3s with `wrong_endpoint` |
| Weather provider live fetch (Los Angeles) | `available=true`, Sunny, 24.1°C |

**Note:** Fixture `1489395` (upcoming) has **no cached prediction** yet (`404 not_cached`). Fresh `POST /api/predict/{id}` runs will attach weather when venue city is valid. Provider fetch verified independently on server.

---

## Before vs after — fixture 1489393

| Field | Before hotfix | After hotfix |
|-------|---------------|--------------|
| `provider_readiness.weather_configured` | `false` (stale) | **`true`** |
| `weather_intelligence.available` | `false` | `false` (correct — frozen snapshot) |
| `weather_intelligence.unavailable_reason` | absent | **`frozen_post_kickoff_snapshot`** |
| `weather_intelligence.provider_now_configured` | absent | **`true`** |

---

## Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/config/provider_readiness.py` | `weather_provider_status()`, richer stamp |
| `worldcup_predictor/api/display_helpers.py` | Re-stamp + weather refresh on serve |
| `worldcup_predictor/api/routes/health.py` | `GET /api/health/providers` |
| `worldcup_predictor/api/routes/predictions.py` | Wrong-path 404 handler |
| `worldcup_predictor/intelligence/weather_intelligence_engine.py` | `unavailable_reason` / `note` fields |
| `scripts/validate_hotfix_weather_config_mismatch.py` | Validation |
| `scripts/deploy_hotfix_weather_production.sh` | Deploy |
| `scripts/deploy_hotfix_weather_smoke.sh` | Smoke |

**Not changed:** WDE, scoring engine, raw probabilities, auth, subscription.

---

## Rollback plan

1. `systemctl stop worldcup-api`
2. Restore from `/opt/worldcup-predictor/backups/deploy-hotfix-weather-20260621-171204/repo_snapshot_pre.tar.gz`
3. `systemctl start worldcup-api`

---

## Final status

```
HOTFIX_WEATHER_CONFIG_MISMATCH = RESOLVED
```

**Correct endpoint:** `GET /api/predict/{fixture_id}`  
**Wrong endpoint:** `/api/predictions/{fixture_id}` → fast 404 with hint

**Frozen historical predictions** will show weather unavailable with an explicit reason — this is expected. **New predictions** for upcoming fixtures with valid city/venue will include live weather intelligence when the provider is configured.
