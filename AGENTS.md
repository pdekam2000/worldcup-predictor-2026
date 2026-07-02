# AGENTS.md

## Cursor Cloud specific instructions

This repository contains two runnable products:

1. **WorldCup Predictor Pro** (primary) — a Python **Streamlit** analytics app for football/soccer match predictions. Root entry points: `worldcup_predictor/ui/gui_app.py` (Streamlit) and `main.py` (CLI). Deps in `requirements.txt`.
2. **worldcup-predictor-web** (`base44-d/`) — a **Vite + React** web frontend that talks to an external Base44 backend. Deps in `base44-d/package.json`.

### Environment / startup notes (non-obvious)

- Python deps are installed into a virtualenv at `.venv` (the update script creates it). Activate with `source .venv/bin/activate`, or call binaries directly (e.g. `.venv/bin/streamlit`). The system Python is 3.12 and is externally managed (PEP 668), so a venv is required — do not `pip install` into the system interpreter.
- The Streamlit app defaults to `APP_ENV=local` and **SQLite** (`data/football_intelligence.db`); **no Postgres is required** to run locally. It also transparently uses an embedded `pgembed` Postgres only if `data/pgembed_dev/database.url` exists — normally it does not, so ignore it.
- The app runs and generates full predictions with **no API keys set**. Without `API_FOOTBALL_KEY`/`SPORTMONKS_API_KEY`/etc., fixtures and predictions use built-in **placeholder** data (e.g. "Home Player 1"), and some panels show "Extended markets unavailable" / missing-odds notices. This is expected local behavior, not a bug. Set keys via a `.env` file (see `.env.production.example`) for live data.
- `.streamlit/config.toml` sets `enableCORS=false` + `enableXsrfProtection=true`; Streamlit prints a warning and forces `enableCORS=true`. Harmless.

### Run commands

- Streamlit (primary): `.venv/bin/streamlit run worldcup_predictor/ui/gui_app.py --server.address 0.0.0.0 --server.port 8501` (health: `GET /_stcore/health`). CLI: `.venv/bin/python main.py <command>` (e.g. `list-competitions`, `gui`).
- Frontend: `npm run dev --prefix base44-d` (Vite dev server on port 5173). Build: `npm run build --prefix base44-d`.

### Lint / test / validate

- There is no formal unit-test suite. Instead `scripts/validate_*.py` are runnable validation/smoke scripts (e.g. `.venv/bin/python scripts/validate_phase49.py`).
- Frontend lint gate used by the deploy guard is `npm run lint:critical --prefix base44-d` (passes). Note: plain `npm run lint --prefix base44-d` currently reports pre-existing unused-import errors — those are code issues, not environment issues.
