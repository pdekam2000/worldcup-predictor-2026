# DATABASE TRUTH AUDIT REPORT

**Phase:** PROJECT-RECOVERY — Part B  
**Date:** 2026-07-02  
**Mode:** Read-only — no merge, no overwrite, no deletion

---

## Executive answers

| Question | Answer |
|----------|--------|
| Which DB has most users? | **Production PostgreSQL** (SaaS auth layer; SQLite has no `users` table) |
| Which DB has most stored predictions? | **Local SQLite** (185 vs production 48) |
| Which DB has most evaluations? | **Local SQLite** (35 vs production 19) |
| Freshest production-live data? | **Production Hetzner SQLite + PostgreSQL** |
| Most complete learning/research data? | **Local PC SQLite** (OddAlerts shadow, CSV imports, larger odds) |
| Copy local DB to production? | **NO** — would overwrite live canonical DB |
| Safe import from local? | **Selective export only** (see §6) |

---

## Canonical decision

| Layer | Canonical source | Path |
|-------|------------------|------|
| **Production football intelligence** | Hetzner SQLite | `/opt/worldcup-predictor/data/football_intelligence.db` |
| **SaaS users / billing / auth** | Hetzner PostgreSQL | via `DATABASE_URL` in `.env.production` |
| **Development / research** | Local PC SQLite | `C:\Users\kaman\Desktop\Footbal\data\football_intelligence.db` |

**Rule:** Production DB remains canonical unless a future approved import plan targets **specific tables/rows**, never full replacement.

---

## Database inventory

### Production SQLite (CANONICAL)

| Metric | Value |
|--------|-------|
| Path | `/opt/worldcup-predictor/data/football_intelligence.db` |
| Size | **9.5 GB** |
| Modified | 2026-07-02 |
| Schema version | **7** |
| Alembic (PG) | `014_enterprise_rbac` (from deploy report) |

| Table | Row count |
|-------|----------:|
| fixtures | 2,161 |
| fixture_results | 1,929 |
| worldcup_stored_predictions | **48** |
| worldcup_prediction_evaluations | **19** |
| odds_snapshots | 1,455 |
| ecse_oddalerts_shadow_predictions | **0** |
| ecse_oddalerts_shadow_monitor | 0 |
| learning_records_v2 | 64 |
| ecse_prediction_snapshots | (present post-migrate; empty on prod) |

**Pre-deploy backup exists:**  
`data/backups/football_intelligence_before_code_deploy_20260701_162213.db` (9.5 GB)

---

### Local PC SQLite (DEVELOPMENT)

| Metric | Value |
|--------|-------|
| Path | `data/football_intelligence.db` |
| Size | **~31.3 GB** |
| Modified | 2026-07-02 |
| Schema version | **7** |

| Table | Row count |
|-------|----------:|
| fixtures | **2,463** (+302 vs prod) |
| fixture_results | **2,216** (+287) |
| worldcup_stored_predictions | **185** (+137) |
| worldcup_prediction_evaluations | **35** (+16) |
| odds_snapshots | **2,236** (+781) |
| ecse_oddalerts_shadow_predictions | **197** |
| ecse_oddalerts_shadow_monitor | 0 |
| ecse_prediction_snapshots | 18 |
| learning_records_v2 | 66 |
| finished fixtures (FT/AET/PEN) | ~2,295 |

**Latest evaluation timestamp (local):** ~2026-06-30  
**Latest prediction update (local):** ~2026-07-01

---

### Local backups (do not delete)

| Backup | Size | Role |
|--------|------|------|
| `football_intelligence_before_oddalerts_csv_promotion_20260701_034614.db` | 27.6 GB | Pre-CSV promotion |
| `football_intelligence_pre_data1d_20260629_090902.db` | 5.1 GB | Matches prod scale (~2161 fixtures) |
| Multiple `pre_data1c/1b` backups | 3.6–4.9 GB | Historical checkpoints |

---

### Other local DBs (non-canonical)

| Path | Role |
|------|------|
| `artifacts/phase*_validation.db` | Test validators only |
| `data/worldcup_predictor.db` | Empty stub |
| `.cache/` | API cache, not intelligence DB |

---

### PostgreSQL (production SaaS)

- Configured via `DATABASE_URL` in `.env.production`
- Holds: `users`, `subscriptions`, `user_settings`, `user_prediction_history`, billing tables
- **Not present on local SQLite** — users live only in PostgreSQL on Hetzner
- Direct query from audit runner failed locally (timeout to remote PG — expected)

**Prior audit note:** Production PostgreSQL is the live auth/billing layer; row counts must be read on server during approved maintenance window.

---

## Comparison summary

| Metric | Production | Local | Winner for prod use |
|--------|----------:|------:|-------------------|
| DB size | 9.5 GB | 31.3 GB | Production (live) |
| Fixtures | 2,161 | 2,463 | Local has more research fixtures |
| Stored predictions | 48 | 185 | Local ahead (owner daily dev) |
| Evaluations | 19 | 35 | Local ahead |
| OddAlerts shadow preds | 0 | 197 | Local only |
| Live user accounts | PG prod | — | **Production only** |

---

## Is local ahead in useful data?

**Yes — for research/owner pipelines, not for replacing production:**

1. **OddAlerts ECSE shadow** — 197 rows local, 0 production  
2. **Owner daily predictions** — 185 local vs 48 production  
3. **Historical CSV / European imports** — large local `data/oddalerts_csv/`, imports (gitignored)  
4. **Extra fixtures** — 302 more fixture rows locally  

**These are NOT safe to bulk-copy** without table-level import plan — risk of duplicate keys, stale odds, or overwriting production-evaluated rows.

---

## Safe import/export plan (recommendation only — DO NOT EXECUTE)

If user approves later:

| Data type | Direction | Method |
|-----------|-----------|--------|
| New prediction rows (owner_daily) | Local → Prod | Export JSON/SQL `INSERT OR IGNORE` by `fixture_id` + `source` |
| OddAlerts shadow predictions | Local → Prod | Table-level copy with conflict check |
| Fixture results missing on prod | Local → Prod | Upsert `fixture_results` only where prod missing |
| Full DB file | **Never** | — |
| CSV bulk / backups | **Never push to prod** | Keep local for research |

Always: **backup production DB first**, dry-run row counts, validate with `validate_owner_daily_prediction_and_eval.py`.

---

## What must NEVER be overwritten

- `/opt/worldcup-predictor/data/football_intelligence.db` (full file)
- Production PostgreSQL (`DATABASE_URL`)
- `/opt/worldcup-predictor/.env.production`
- `data/backups/*` on production
- Production runtime: `data/sportmonks_dump/`, shadow jsonl, user session data

---

## Recommendation (Part B)

**NEED_DB_IMPORT_PLAN** — only if you want local research predictions/shadow data on production.  
**Default:** keep production DB canonical; run owner pipelines **on production** to populate predictions there.

---

*Read-only audit script: `scripts/_db_truth_audit_readonly.py`*  
*Prior inventory: `artifacts/project_database_inventory_20260701.json`*
