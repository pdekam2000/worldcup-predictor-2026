#!/usr/bin/env bash
# Phase A22 — pack backend + frontend for production deploy
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="/tmp/phase_a22_deploy.tar.gz"
cd "$ROOT"
tar czf "$OUT" \
  worldcup_predictor/elite_orchestrator/shadow_jsonl_io.py \
  worldcup_predictor/elite_orchestrator/shadow_health.py \
  worldcup_predictor/elite_orchestrator/shadow_queue.py \
  worldcup_predictor/elite_orchestrator/autonomous_shadow_cycle.py \
  worldcup_predictor/elite_orchestrator/shadow_scheduler.py \
  worldcup_predictor/elite_orchestrator/shadow_admin.py \
  worldcup_predictor/elite_orchestrator/shadow_store.py \
  worldcup_predictor/elite_orchestrator/pairing.py \
  worldcup_predictor/elite_orchestrator/fixture_selector.py \
  worldcup_predictor/predops/snapshots.py \
  worldcup_predictor/root_cause/knowledge_store.py \
  worldcup_predictor/config/settings.py \
  worldcup_predictor/cli/commands.py \
  worldcup_predictor/api/routes/admin_elite_shadow.py \
  main.py \
  deployment/systemd/worldcup-elite-shadow.service \
  deployment/systemd/worldcup-elite-shadow.timer \
  scripts/validate_phase_a22_shadow_runtime.py \
  scripts/deploy_phase_a22_smoke.sh \
  scripts/_remote_deploy_phase_a22.sh
echo "PACKED $OUT"
