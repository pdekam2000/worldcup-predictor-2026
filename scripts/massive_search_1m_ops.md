# Massive Search 1M ops (NOT LAUNCHED)

Scale decision after 100k audit: `SCALE_TO_1M_NOT_STATISTICALLY_JUSTIFIED`.

Do **not** start the 1M run until labeled corpus grows (usable prematch N ≫ 225 and validation can support N≥50 gates).

If a future audit flips to APPROVED, use these local commands (PowerShell, non-interactive):

## Start (resume from completed 100k toward 1M)

```powershell
$env:PYTHONUNBUFFERED = "1"
$out = "artifacts/massive_algorithm_search/20260802T193933Z"
Start-Process -FilePath python -ArgumentList @(
  "scripts/run_massive_algorithm_search_foundation.py",
  "--resume", "--out", $out, "--target", "1000000"
) -RedirectStandardOutput "$out/run_1m.stdout.log" -RedirectStandardError "$out/run_1m.stderr.log" -WindowStyle Hidden
```

## Inspect status

```powershell
Get-Content artifacts/massive_algorithm_search/20260802T193933Z/experiment_checkpoint.json
Get-Content artifacts/massive_algorithm_search/20260802T193933Z/progress_history.jsonl -Tail 5
```

## Tail sanitized progress

```powershell
Get-Content artifacts/massive_algorithm_search/20260802T193933Z/progress_history.jsonl -Wait -Tail 20
```

## Stop gracefully

Stop by creating a stop flag if supported, or terminate the Python PID after the next checkpoint interval (prefer waiting for checkpoint write).

```powershell
# After confirming PID from Start-Process / Get-Process python
Stop-Process -Id <PID> -ErrorAction SilentlyContinue
```

## Resume

Same as Start (dedup via `seen_hashes.txt` / checkpoint offset).

## Interim report

```powershell
python -m worldcup_predictor.research.massive_algorithm_search.audit_100k
```

## Verify completion

```powershell
python -c "import json; c=json.load(open('artifacts/massive_algorithm_search/20260802T193933Z/experiment_checkpoint.json')); print(c['tested'], c['unique'], c['target_n'])"
```

Expected when done: `tested == unique == 1000000` with prior 100k counted (≈900k new).

Constraints: no API calls, read-only DB, sealed holdout unopened, no production writes, no auto-promotion.
