# FULL-PROJECT-SYNC-2 — targeted safe staging (no blind git add .)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))

# Source trees
git add worldcup_predictor/
git add base44-d/src/

# Scripts — new validators and pipeline tooling
$scriptGlobs = @(
  "scripts/run_production_prediction_pipeline.py",
  "scripts/run_odds_freshness_refresh.py",
  "scripts/run_*_1*.py",
  "scripts/sync_wc_upcoming_fixtures.py",
  "scripts/audit_wc_fixture_schedule.py",
  "scripts/audit_odds_timestamp_formats.py",
  "scripts/find_next_knockout_fixture.py",
  "scripts/discover_controlled_knockout_predictions_2.py",
  "scripts/run_controlled_knockout_predictions_2.py",
  "scripts/inspect_*.py",
  "scripts/capture_match_eval_1567310_prematch.py",
  "scripts/validate_*.py",
  "scripts/run_codebase_consolidation_2.py",
  "scripts/run_codebase_consolidation_2_production_deploy.sh",
  "scripts/run_full_production_match_report.py"
)
foreach ($g in $scriptGlobs) {
  Get-ChildItem -Path $g -ErrorAction SilentlyContinue | ForEach-Object { git add $_.FullName.Replace((Get-Location).Path + "\", "").Replace("\", "/") }
}

# Phase reports and sync docs (root markdown)
$mdFiles = Get-ChildItem -Path . -Filter "*.md" -File | Where-Object {
  $_.Name -notmatch "PRODUCTION_PIPELINE_LAST_RUN|ODDS_FRESHNESS_1_LAST_RUN"
}
foreach ($f in $mdFiles) { git add $f.Name }

# Deployment snippet (no secrets)
if (Test-Path "deployment/ecse_x2_m7_enablement_snippet.env") {
  git add deployment/ecse_x2_m7_enablement_snippet.env
}

Write-Host "STAGED:"
git diff --cached --stat
