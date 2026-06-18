# PostgreSQL SaaS Architecture (Phase 1)

## Overview

Production SaaS data lives in **PostgreSQL** via SQLAlchemy 2.0 models and Alembic migrations.

| Layer | Store | Scope |
|-------|-------|-------|
| **SaaS / users** | PostgreSQL | Auth users, settings, favorites, alerts, notifications, subscriptions, prediction history |
| **Intelligence / engine** | SQLite (`data/football_intelligence.db`) | Fixtures, predictions, caches, learning — **unchanged in Phase 1** |

```
┌─────────────────────────────────────────────────────────────┐
│                     React Frontend                          │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP /api/*
┌───────────────────────────▼─────────────────────────────────┐
│                     FastAPI (Phase 2+)                      │
│  ┌─────────────────────┐    ┌─────────────────────────────┐ │
│  │ SaaS repositories   │    │ Predict pipeline (unchanged)│ │
│  │ saas_factory.uow    │    │ FootballIntelligenceRepo    │ │
│  └──────────┬──────────┘    └──────────────┬──────────────┘ │
└─────────────┼──────────────────────────────┼────────────────┘
              │                              │
     ┌────────▼────────┐            ┌────────▼────────┐
     │   PostgreSQL    │            │     SQLite      │
     │  (DATABASE_URL) │            │ intelligence DB │
     └─────────────────┘            └─────────────────┘
```

## Tables (Phase 1)

| Table | Model | Purpose |
|-------|-------|---------|
| `users` | `User` | Accounts, roles, password_hash (Phase 2 auth) |
| `user_settings` | `UserSettings` | Language, timezone, JSONB preferences |
| `user_favorites` | `UserFavorite` | Team/league/match favorites |
| `user_alerts` | `UserAlert` | User alert feed |
| `user_notifications` | `UserNotification` | In-app notifications |
| `subscriptions` | `Subscription` | Plan, billing, status |
| `user_prediction_history` | `UserPredictionHistory` | Per-user prediction views |

All tables use `UUID` primary keys (except settings: `user_id` PK). FK `ON DELETE CASCADE` from `users`.

## Repository structure

```
worldcup_predictor/database/
  postgres/
    base.py              # DeclarativeBase
    models.py            # ORM models
    enums.py             # Python enums
    schemas.py           # Immutable record DTOs
    session.py           # Engine + session_scope
    uow.py               # SaasUnitOfWork
    repositories/
      users.py
      settings.py
      favorites.py
      alerts.py
      notifications.py
      subscriptions.py
      prediction_history.py
  saas_factory.py        # require_postgres(), saas_uow()
```

### Usage (Phase 2+)

```python
from worldcup_predictor.database.saas_factory import saas_uow

with saas_uow() as uow:
    user = uow.users.create(email="a@b.com")
    uow.settings.get_or_create(user.id)
    uow.subscriptions.get_or_create_free(user.id)
```

## Migrations

```bash
# Requires DATABASE_URL in .env
pip install -r requirements.txt
alembic upgrade head
```

Revision: `001_saas_initial` — creates all Phase 1 tables and PostgreSQL enums.

## Settings

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection (required for SaaS repos) |
| `APP_ENV` | `local` (default) or `production` |
| `SQLITE_PATH` | Intelligence DB — unchanged |

Production (`APP_ENV=production`) will require `DATABASE_URL` when SaaS code paths are wired in Phase 2.

## Phase 2 — JWT auth (current)

FastAPI auth (`/api/auth/*`) uses **PostgreSQL only** via `saas_uow()`:

- Passwords: **bcrypt** (`worldcup_predictor/auth/passwords.py`)
- Tokens: **JWT access** (`worldcup_predictor/auth/jwt_tokens.py`)
- `PUBLIC_ACCESS_CODE`: invite gate on **register** only (not stored as user password)
- `ADMIN_USERNAME` / `ADMIN_PASSWORD`: bootstrap admin login → PostgreSQL `users.role = admin`
- New users auto-provision `user_settings` + free `subscriptions` row

SQLite `access` tables are **no longer used** by FastAPI auth (Streamlit GUI unchanged).

| Endpoint | Auth store |
|----------|------------|
| `POST /api/auth/register` | PostgreSQL |
| `POST /api/auth/login` | PostgreSQL + bcrypt |
| `GET /api/auth/me` | JWT → PostgreSQL user lookup |
| `POST /api/auth/logout` | Client clears JWT (stateless) |

## What later phases still do NOT do

- No data migration from SQLite intelligence DB
- No changes to agents, prediction engine, API-Football, or Sportmonks
- No deployment
