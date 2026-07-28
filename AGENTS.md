# AGENTS.md

## Cursor Cloud specific instructions

This is **WorldCup Predictor Pro** — a single Streamlit web app for analytical football
match predictions (multi-agent prediction pipeline). Analytical only; not betting advice.

### Environment
- System Python (`/usr/bin/python3`, 3.12) is PEP 668 externally-managed, so dependencies
  live in a project virtualenv at `.venv` (created by the startup update script). Activate it
  with `. .venv/bin/activate`, or call binaries directly as `.venv/bin/python` / `.venv/bin/streamlit`.
- Python deps come from `requirements.txt`. `pytest` is installed for tests but is not listed there.

### Run the app (development)
- Preferred: `.venv/bin/streamlit run worldcup_predictor/ui/gui_app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true`
- `python main.py gui` also works (it just shells out to the same `streamlit run`).
- Health check: `curl http://127.0.0.1:8501/_stcore/health` returns `200`.
- No secrets/API keys are required to boot. Auth and the paywall are OFF by default
  (`APP_AUTH_ENABLED` and `PUBLIC_ACCESS_ENABLED` default to false); live data providers
  (`API_FOOTBALL_KEY`, `OPENAI_API_KEY`, etc.) are optional and only enrich predictions.
- `main.py` is a broader CLI with many subcommands (`upcoming`, `api`, `db-test`, etc.);
  run `python main.py -h` to list them.

### Test / lint
- Tests: `.venv/bin/python -m pytest tests/` (a small suite of ~19 tests; there is no pytest config file).
- There is no configured linter in the repo.

### Notes
- The repo root is cluttered with many `*.md` audit/phase reports and `*.tar.gz` deploy
  archives; the actual application code lives under `worldcup_predictor/`.
- Runtime data (SQLite DBs, caches, reports under `data/`, `.cache/`, `reports/`) is
  gitignored and created on demand.
