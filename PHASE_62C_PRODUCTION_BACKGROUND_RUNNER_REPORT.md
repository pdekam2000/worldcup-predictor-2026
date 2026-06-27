# PHASE 62C — Production Safe Background Runner Report

**Generated:** 2026-06-26  
**Mode:** Ops hardening only — no model, UI, or public flag changes

## Root cause

Production Phase 62/62B was started over an interactive SSH session. After ~2 hours the SSH client disconnected with `Connection reset` (exit code 255). The pipeline was killed with the session — this is a **session lifecycle issue**, not a confirmed script failure.

## Solution

Phase 62C adds:

1. **Background launcher** — `scripts/phase62c_production_background_runner.sh` (nohup, survives SSH disconnect)
2. **Progress checkpoint** — `data/validation/phase62b_progress.json` (resume-safe)
3. **Flush logging** — progress every N fixtures with API/cache/xG/lineup counts + ETA
4. **Finalize script** — `scripts/phase62c_finalize_and_validate.sh`

## Recommended production command

```bash
cd /opt/worldcup-predictor
bash scripts/phase62c_production_background_runner.sh
```

Equivalent manual command:

```bash
cd /opt/worldcup-predictor
set -a && . ./.env.production && set +a

nohup .venv/bin/python scripts/phase62b_sportmonks_wc_xg_lineups_completion.py \
  --max-sm-calls 200 --progress-every 5 > /tmp/phase62b.log 2>&1 &
```

Immediately record:

| Field | Value |
|-------|-------|
| PID | output of `echo $!` after nohup |
| Log path | `/tmp/phase62b.log` |
| Checkpoint | `data/validation/phase62b_progress.json` |

## Live monitor commands

```bash
tail -f /tmp/phase62b.log
ps aux | grep phase62b
pgrep -af phase62b
du -sh data/
ls -lh data/validation/
cat data/validation/phase62b_progress.json
```

## Resume safety

Before rerun, inspect partial outputs:

| Artifact | Path |
|----------|------|
| Progress checkpoint | `data/validation/phase62b_progress.json` |
| Mapping audit | `data/validation/phase62b_mapping_audit.json` |
| Completion JSON | `data/validation/phase62b_sportmonks_wc_completion.json` |
| Sportmonks raw cache | `data/egie/world_cup/raw/sportmonks/*.json` |
| Enriched features | `data/egie/world_cup/raw/goal_timing_features_enriched/*.json` |

**Resume behavior (Phase 62C):**

- Skips fixtures already in checkpoint `completed_fixture_ids`
- Skips fixtures with Sportmonks cache file + xG snapshot or lineups enrichment
- Cache-first: no duplicate API call when `data/egie/world_cup/raw/sportmonks/{sm_id}.json` exists
- Checkpoint updated every `--progress-every` fixtures (default 5)
- Use `--no-resume` only for forced full rerun

## Checkpoint schema

`data/validation/phase62b_progress.json`:

```json
{
  "started_at": "ISO8601",
  "updated_at": "ISO8601",
  "last_fixture_id": 1489369,
  "processed_count": 42,
  "success_count": 38,
  "failed_count": 4,
  "skipped_cached_count": 12,
  "api_calls_used": 30,
  "cache_hits": 18,
  "xg_found": 25,
  "xg_missing": 17,
  "lineups_found": 30,
  "lineups_missing": 12,
  "status": "running|completed",
  "completed_fixture_ids": []
}
```

## Logging sample

```
[phase62b] fixture=1489369 sm=18882619 progress=15/47 api_calls=8 cache_hits=7 xg=10/5 lineups=12/3 errors=2 eta_min=4
```

Logs flush on each progress line (unbuffered stdout).

## Finalization (after background job ends)

```bash
cd /opt/worldcup-predictor
bash scripts/phase62c_finalize_and_validate.sh
```

Confirms:

- No `phase62b` process still running
- `scripts/validate_phase62b_sportmonks_wc_xg_lineups_completion.py` passes
- Report, validation JSON, mapping audit, checkpoint, enriched rows exist

## Local validation

`scripts/validate_phase62c_production_background_runner.py` — verifies runner scripts, checkpoint R/W, resume flags.

## Production run status

| Item | Status |
|------|--------|
| Background runner deployed | **Yes** (`phase62c_production_background_runner.sh`) |
| Production job launched | **Yes** — PID **389056** |
| Log file | `/tmp/phase62b.log` |
| Pre-existing artifacts | mapping audit + completion JSON present; 319M raw cache |
| Phase 61B rerun | **Not authorized** |
| Public flags | **Unchanged** |

Monitor until complete:

```bash
tail -f /tmp/phase62b.log
pgrep -af phase62b
cat /opt/worldcup-predictor/data/validation/phase62b_progress.json
```

Then finalize:

```bash
cd /opt/worldcup-predictor && bash scripts/phase62c_finalize_and_validate.sh
```

## Next recommendation

1. Deploy Phase 62C files to `/opt/worldcup-predictor`
2. Run `bash scripts/phase62c_production_background_runner.sh`
3. Monitor `/tmp/phase62b.log` until checkpoint `status=completed`
4. Run `bash scripts/phase62c_finalize_and_validate.sh`
5. Review `PHASE_62B_SPORTMONKS_WC_XG_LINEUPS_COMPLETION_REPORT.md` recommendation

Expected recommendation remains **`PROVIDER_LIMITED`** or **`NEED_MORE_IMPORTS`** until Sportmonks xG/lineups coverage improves and fixture count exceeds 500.

---
*Phase 62C — ops only. No model or public rollout changes.*
