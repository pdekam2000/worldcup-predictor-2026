#!/usr/bin/env bash
# Phase A21C â€” no-op detached deploy test (infrastructure only).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${WC_DEPLOY_CHILD:-}" ]] && [[ "${DEPLOY_FOREGROUND:-0}" != "1" ]]; then
  exec bash "${SCRIPT_DIR}/deploy_run.sh" "$0" "$@"
fi

# shellcheck source=lib/deploy_hardening.sh
source "${SCRIPT_DIR}/lib/deploy_hardening.sh"

deploy_init "noop_test"
trap 'deploy_release_lock' EXIT
deploy_acquire_lock || exit 3
deploy_record_rollback "noop_test_no_app_changes backup=none"

deploy_run_step noop_wait sleep 3
deploy_run_step noop_ok /bin/true

deploy_finish_ok
exit 0
