#!/usr/bin/env bash
# Phase 1 — PROPOSAL ONLY: bootstrap restricted deploy user on Hetzner.
# DO NOT run from CI. DO NOT run until explicitly approved by server administrator.
# Does NOT modify sshd_config. Does NOT disable root login or password authentication.

set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
PUBLIC_KEY_FILE=""
PUBLIC_KEY="${DEPLOY_PUBLIC_KEY:-}"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: bootstrap_hetzner_deploy_user.sh [--public-key-file PATH] [--dry-run]

Environment:
  DEPLOY_PUBLIC_KEY   SSH public key string (ed25519 recommended)

Requirements:
  - Must be run as root (one-time administrator bootstrap)
  - Does NOT modify sshd_config in Phase 1
  - Does NOT disable root login
  - Does NOT configure unrestricted sudo

After bootstrap, install deployment/sudoers/worldcup-deploy separately (manual review).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --public-key-file)
      PUBLIC_KEY_FILE="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "ERROR: must run as root (one-time admin bootstrap)." >&2
  exit 1
fi

if [[ -n "${PUBLIC_KEY_FILE}" ]]; then
  if [[ ! -f "${PUBLIC_KEY_FILE}" ]]; then
    echo "ERROR: public key file not found: ${PUBLIC_KEY_FILE}" >&2
    exit 1
  fi
  PUBLIC_KEY="$(tr -d '\r' < "${PUBLIC_KEY_FILE}")"
fi

if [[ -z "${PUBLIC_KEY}" ]]; then
  echo "ERROR: supply DEPLOY_PUBLIC_KEY or --public-key-file" >&2
  exit 1
fi

# Basic public key shape validation (no secrets stored in script).
if [[ "$(echo "${PUBLIC_KEY}" | awk '{print NF}')" -lt 2 ]]; then
  echo "ERROR: public key must look like: <type> <base64> [comment]" >&2
  exit 1
fi

HOME_DIR="/home/${DEPLOY_USER}"
SSH_DIR="${HOME_DIR}/.ssh"
AUTH_KEYS="${SSH_DIR}/authorized_keys"

if id "${DEPLOY_USER}" >/dev/null 2>&1; then
  echo "INFO: user ${DEPLOY_USER} already exists — preserving."
else
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[dry-run] useradd -m -s /bin/bash ${DEPLOY_USER}"
  else
    useradd -m -s /bin/bash "${DEPLOY_USER}"
    echo "INFO: created user ${DEPLOY_USER}"
  fi
fi

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "[dry-run] mkdir -p ${SSH_DIR} && chmod 700 ${SSH_DIR}"
  echo "[dry-run] append public key to ${AUTH_KEYS} if missing"
  echo "[dry-run] chown -R ${DEPLOY_USER}:${DEPLOY_USER} ${SSH_DIR}"
  echo "[dry-run] chmod 600 ${AUTH_KEYS}"
  exit 0
fi

mkdir -p "${SSH_DIR}"
chmod 700 "${SSH_DIR}"

existing=""
if [[ -f "${AUTH_KEYS}" ]]; then
  existing="$(cat "${AUTH_KEYS}")"
fi

key_body="$(echo "${PUBLIC_KEY}" | awk '{print $2}')"
appended=0
if [[ -f "${AUTH_KEYS}" ]] && grep -qF "${key_body}" "${AUTH_KEYS}"; then
  echo "INFO: public key already present in authorized_keys — not duplicated."
else
  if [[ -s "${AUTH_KEYS}" ]] && [[ -n "$(tail -c1 "${AUTH_KEYS}" 2>/dev/null || true)" ]]; then
    echo >> "${AUTH_KEYS}"
  fi
  echo "${PUBLIC_KEY}" >> "${AUTH_KEYS}"
  appended=1
  echo "INFO: appended public key to authorized_keys"
fi

chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${SSH_DIR}"
chmod 600 "${AUTH_KEYS}"

echo "OK: deploy user SSH bootstrap complete (user=${DEPLOY_USER}, key_appended=${appended})"
echo "NOTE: install restricted sudo separately: deployment/sudoers/worldcup-deploy"
echo "NOTE: sshd hardening (PasswordAuthentication, PermitRootLogin) is NOT changed by this script."
