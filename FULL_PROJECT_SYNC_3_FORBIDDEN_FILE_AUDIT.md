# FULL-PROJECT-SYNC-3 — Forbidden File Audit

**Status:** `STAGING_SAFE`

## Pre-commit scan

| Pattern | Found in staging? |
|---|---|
| `*.db` / `*.sqlite*` | No |
| `.env` / `.env.*` | No |
| `*.pem` / `*.key` / credentials | No |
| `data/shadow/` | No |
| `data/cache/` | No |
| `.cache/` | No |
| `*.log` / `logs/` | No |
| Large JSONL (>1MB) | No |
| `node_modules/` / `.venv/` | No |
| Provider dumps | No |
| `parity_repair_export.json` | No (script name matched grep only) |

## Staged commit

- **100 files** in `dc51f80`
- All under `worldcup_predictor/`, `scripts/`, `tests/`, `*.md`
- No runtime or secret files

## Post-commit local untracked (correctly excluded)

- `data/shadow/*.jsonl` (modified, unstaged)
- `artifacts/` (gitignored)
