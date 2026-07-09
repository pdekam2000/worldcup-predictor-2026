#!/usr/bin/env bash
# Approved ops wrapper — status for worldcup-api only (fixed service name).
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

exec "${SYSTEMCTL}" status "${SERVICE}" --no-pager
