#!/usr/bin/env bash
set -euo pipefail
APP=/opt/worldcup-predictor
TARBALL=/tmp/hotfix_h3b_shadow_jsonl.tar.gz
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/shadow-jsonl-restore-${TS}"
LOG="${BACKUP}.log"
mkdir -p "${BACKUP}"
exec > >(tee "${LOG}") 2>&1
echo "=== H3B Shadow JSONL Restore ${TS} ==="
[ -f "${TARBALL}" ] || { echo TARBALL_MISSING; exit 1; }
for f in \
  "${APP}/data/shadow/elite_orchestrator_predictions.jsonl" \
  "${APP}/data/shadow/elite_orchestrator_evaluations.jsonl" \
  "${APP}/data/shadow/root_cause_store/knowledge_records.jsonl"
do
  if [ -f "${f}" ]; then
    rel="${f#${APP}/}"
    mkdir -p "${BACKUP}/$(dirname "${rel}")"
    cp -a "${f}" "${BACKUP}/${rel}"
    echo "Backed up ${rel}"
  fi
done
tar xzf "${TARBALL}" -C "${APP}"
chown www-data:www-data \
  "${APP}/data/shadow/elite_orchestrator_predictions.jsonl" \
  "${APP}/data/shadow/elite_orchestrator_evaluations.jsonl" \
  "${APP}/data/shadow/root_cause_store/knowledge_records.jsonl" 2>/dev/null || true
chmod 644 \
  "${APP}/data/shadow/elite_orchestrator_predictions.jsonl" \
  "${APP}/data/shadow/elite_orchestrator_evaluations.jsonl" \
  "${APP}/data/shadow/root_cause_store/knowledge_records.jsonl"
chmod 755 "${APP}/data/shadow/root_cause_store" 2>/dev/null || true
wc -l \
  "${APP}/data/shadow/elite_orchestrator_predictions.jsonl" \
  "${APP}/data/shadow/elite_orchestrator_evaluations.jsonl" \
  "${APP}/data/shadow/root_cause_store/knowledge_records.jsonl"
sudo -u www-data test -r "${APP}/data/shadow/elite_orchestrator_predictions.jsonl" && echo OK_predictions
sudo -u www-data test -r "${APP}/data/shadow/elite_orchestrator_evaluations.jsonl" && echo OK_evaluations
sudo -u www-data test -r "${APP}/data/shadow/root_cause_store/knowledge_records.jsonl" && echo OK_root_cause
"${APP}/.venv/bin/python" -c "from worldcup_predictor.admin.elite_shadow_preview import EliteShadowPreviewService; import json; print(json.dumps(EliteShadowPreviewService().preview_summary(), indent=2))"
echo RESTORE_OK backup=${BACKUP}
