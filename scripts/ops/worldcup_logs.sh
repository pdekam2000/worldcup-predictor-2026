#!/usr/bin/env bash
# Approved ops wrapper — journalctl for worldcup-api only; bounded line count.
set -euo pipefail

SERVICE="worldcup-api"
DEFAULT_LINES=100
MAX_LINES=500
JOURNALCTL="${JOURNALCTL:-/bin/journalctl}"

if [[ $# -gt 1 ]]; then
  echo "Usage: $0 [lines]" >&2
  exit 2
fi

raw="${1:-$DEFAULT_LINES}"
if ! [[ "${raw}" =~ ^[0-9]+$ ]]; then
  echo "lines must be a positive integer" >&2
  exit 2
fi
lines="${raw}"
if (( lines < 1 )); then
  echo "lines must be at least 1" >&2
  exit 2
fi
if (( lines > MAX_LINES )); then
  echo "lines must not exceed ${MAX_LINES}" >&2
  exit 2
fi

if [[ ! -x "${JOURNALCTL}" ]]; then
  JOURNALCTL="$(command -v journalctl || true)"
fi
if [[ -z "${JOURNALCTL}" ]]; then
  echo "journalctl not found" >&2
  exit 1
fi

exec "${JOURNALCTL}" -u "${SERVICE}" -n "${lines}" --no-pager
