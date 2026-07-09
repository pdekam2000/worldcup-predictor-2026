#!/usr/bin/env bash
# Phase 3.3 — install OpenAI tunnel-client for WorldCup MCP (preparation only).
# Official source: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
# Binary releases: https://github.com/openai/tunnel-client/releases/latest
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/worldcup-predictor}"
INSTALL_BIN="${INSTALL_BIN:-/usr/local/bin/tunnel-client}"
TUNNEL_USER="${TUNNEL_USER:-worldcup-mcp-tunnel}"
TUNNEL_GROUP="${TUNNEL_GROUP:-worldcup-mcp-tunnel}"
ENV_DIR="/etc/worldcup-mcp-tunnel"
ENV_FILE="${ENV_DIR}/environment"
ENV_EXAMPLE="${ENV_DIR}/environment.example"
PROFILE_NAME="worldcup-predictor"
GITHUB_RELEASE_API="https://api.github.com/repos/openai/tunnel-client/releases/latest"
MCP_LOCAL_URL="http://127.0.0.1:8765/mcp"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run as root" >&2
  exit 1
fi

echo "==> Phase 3.3 tunnel-client install (prepare only)"

detect_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo "amd64" ;;
    aarch64|arm64) echo "arm64" ;;
    *)
      echo "ERROR: unsupported architecture: $(uname -m)" >&2
      exit 1
      ;;
  esac
}

detect_os() {
  case "$(uname -s)" in
    Linux) echo "linux" ;;
    *)
      echo "ERROR: unsupported OS: $(uname -s) (official tunnel-client ships linux/darwin archives)" >&2
      exit 1
      ;;
  esac
}

ARCH="$(detect_arch)"
OS="$(detect_os)"
echo "platform=${OS}-${ARCH}"

if [[ ! -d "${APP_ROOT}/.git" ]]; then
  echo "WARN: APP_ROOT ${APP_ROOT} is not a git checkout" >&2
fi

if ! id "${TUNNEL_USER}" >/dev/null 2>&1; then
  useradd --system --home /var/lib/worldcup-mcp-tunnel --shell /usr/sbin/nologin "${TUNNEL_USER}"
  echo "Created service user ${TUNNEL_USER}"
fi

install -d -m 0750 -o root -g "${TUNNEL_GROUP}" "${ENV_DIR}"
install -d -m 0750 -o "${TUNNEL_USER}" -g "${TUNNEL_GROUP}" /var/lib/worldcup-mcp-tunnel

if [[ ! -f "${ENV_EXAMPLE}" ]]; then
  cat >"${ENV_EXAMPLE}" <<'EOF'
# /etc/worldcup-mcp-tunnel/environment — copy to environment and chmod 0640
# Never commit real values. Obtain from Platform:
# https://platform.openai.com/settings/organization/tunnels
# https://platform.openai.com/settings/organization/api-keys

CONTROL_PLANE_API_KEY=
CONTROL_PLANE_TUNNEL_ID=tunnel_
MCP_SERVER_URL=http://127.0.0.1:8765/mcp
# If worldcup-mcp requires MCP_AUTH_TOKEN for streamable-http:
MCP_AUTHORIZATION_HEADER=Bearer

HEALTH_LISTEN_ADDR=127.0.0.1:8081
EOF
  chmod 0640 "${ENV_EXAMPLE}"
  chown root:"${TUNNEL_GROUP}" "${ENV_EXAMPLE}"
fi

if [[ -f "${INSTALL_BIN}" ]]; then
  echo "tunnel-client already present: ${INSTALL_BIN}"
  "${INSTALL_BIN}" --version || true
else
  echo "==> Resolving latest official release metadata"
  RELEASE_JSON="$(curl -fsSL "${GITHUB_RELEASE_API}")"
  VERSION="$(printf '%s' "${RELEASE_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')"
  echo "latest_release=${VERSION}"

  ASSET_NAME="tunnel-client_${OS}_${ARCH}.zip"
  ASSET_URL="$(printf '%s' "${RELEASE_JSON}" | python3 -c "import json,sys; assets=json.load(sys.stdin)['assets']; print(next(a['browser_download_url'] for a in assets if a['name']=='${ASSET_NAME}'))")"
  CHECKSUMS_URL="$(printf '%s' "${RELEASE_JSON}" | python3 -c "import json,sys; assets=json.load(sys.stdin)['assets']; print(next(a['browser_download_url'] for a in assets if a['name']=='SHA256SUMS.txt'))")"

  WORK="$(mktemp -d)"
  trap 'rm -rf "${WORK}"' EXIT
  curl -fsSL "${ASSET_URL}" -o "${WORK}/${ASSET_NAME}"
  curl -fsSL "${CHECKSUMS_URL}" -o "${WORK}/SHA256SUMS.txt"
  (
    cd "${WORK}"
    grep " ${ASSET_NAME}$" SHA256SUMS.txt | sha256sum -c -
  )
  unzip -q "${WORK}/${ASSET_NAME}" -d "${WORK}/extract"
  BIN_PATH="$(find "${WORK}/extract" -type f -name tunnel-client | head -1)"
  if [[ -z "${BIN_PATH}" ]]; then
    echo "ERROR: tunnel-client binary not found in release archive" >&2
    exit 1
  fi
  install -m 0755 "${BIN_PATH}" "${INSTALL_BIN}"
  echo "Installed ${INSTALL_BIN}"
  "${INSTALL_BIN}" --version
fi

echo "==> Installing systemd unit (disabled by default)"
install -m 0644 "${APP_ROOT}/deployment/systemd/worldcup-mcp-tunnel.service" /etc/systemd/system/worldcup-mcp-tunnel.service
systemctl daemon-reload

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "NOTE: ${ENV_FILE} not found. Tunnel will NOT be enabled."
  echo "Copy ${ENV_EXAMPLE} to ${ENV_FILE}, fill credentials, chmod 0640, chown root:${TUNNEL_GROUP}"
  echo "Install complete (credentials missing — tunnel not started)."
  exit 0
fi

chmod 0640 "${ENV_FILE}"
chown root:"${TUNNEL_GROUP}"

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

if [[ -z "${CONTROL_PLANE_API_KEY:-}" || -z "${CONTROL_PLANE_TUNNEL_ID:-}" ]]; then
  echo "NOTE: CONTROL_PLANE_API_KEY or CONTROL_PLANE_TUNNEL_ID empty — tunnel not configured."
  exit 0
fi

echo "==> Initializing tunnel profile ${PROFILE_NAME} (remote HTTP MCP)"
sudo -u "${TUNNEL_USER}" env \
  CONTROL_PLANE_API_KEY="${CONTROL_PLANE_API_KEY}" \
  CONTROL_PLANE_TUNNEL_ID="${CONTROL_PLANE_TUNNEL_ID}" \
  MCP_SERVER_URL="${MCP_SERVER_URL:-${MCP_LOCAL_URL}}" \
  "${INSTALL_BIN}" init \
  --sample sample_mcp_remote_no_auth \
  --profile "${PROFILE_NAME}" \
  --tunnel-id "${CONTROL_PLANE_TUNNEL_ID}" \
  --mcp-server-url "${MCP_SERVER_URL:-${MCP_LOCAL_URL}}"

echo "==> Doctor check"
sudo -u "${TUNNEL_USER}" env \
  CONTROL_PLANE_API_KEY="${CONTROL_PLANE_API_KEY}" \
  CONTROL_PLANE_TUNNEL_ID="${CONTROL_PLANE_TUNNEL_ID}" \
  "${INSTALL_BIN}" doctor --profile "${PROFILE_NAME}" --explain

echo "==> Enable/start deferred to owner approval"
echo "When approved: systemctl enable --now worldcup-mcp-tunnel.service"
echo "Rollback: systemctl disable --now worldcup-mcp-tunnel.service"
