#!/usr/bin/env bash
# Pack HOTFIX H3B — Elite Shadow JSONL restore (data only)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/hotfix_h3b_shadow_jsonl.tar.gz}"

cd "${ROOT}"
for f in \
  data/shadow/elite_orchestrator_predictions.jsonl \
  data/shadow/elite_orchestrator_evaluations.jsonl \
  data/shadow/root_cause_store/knowledge_records.jsonl
do
  if [ ! -f "${f}" ]; then
    echo "MISSING: ${f}" >&2
    exit 1
  fi
done

tar czf "${OUT}" \
  data/shadow/elite_orchestrator_predictions.jsonl \
  data/shadow/elite_orchestrator_evaluations.jsonl \
  data/shadow/root_cause_store/knowledge_records.jsonl

echo "PACKED: ${OUT}"
wc -l data/shadow/elite_orchestrator_predictions.jsonl \
      data/shadow/elite_orchestrator_evaluations.jsonl \
      data/shadow/root_cause_store/knowledge_records.jsonl
ls -lh "${OUT}"
