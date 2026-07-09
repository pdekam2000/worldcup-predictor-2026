#!/usr/bin/env bash
# Approved ops wrapper — restart worldcup-api only; verify active afterward.
set -euo pipefail

SERVICE="worldcup-api"
SYSTEMCTL="${SYSTEMCTL:-/bin/systemctl}"

if [[ ! -x "${SYSTEMCTL}" ]]; then
  SYSTEMCTL="$(command -v systemctl || true)"
fi
if [[ -z "${SYSTEMCTL}" ]]; then
  echo "systemctl not found" >&2
  exit 1
fi

"${SYSTEMCTL}" restart "${SERVICE}"
sleep 2
if ! "${SYSTEMCTL}" is-active --quiet "${SERVICE}"; then
  echo "ERROR: ${SERVICE} is not active after restart" >&2
  "${SYSTEMCTL}" status "${SERVICE}" --no-pager >&2 || true
  exit 1
fi
echo "OK: ${SERVICE} is active"
