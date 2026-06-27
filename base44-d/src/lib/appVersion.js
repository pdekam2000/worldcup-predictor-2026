/**
 * Frontend build version — keep in sync with /app_version.manifest.json (Hotfix Pack 4).
 * Updated on each deploy via scripts/sync_app_version_metadata.py
 */

export const APP_VERSION = "A23.0.0";
export const BUILD_LABEL = "hotfix-pack4";
export const BUILD_DATE = "2026-06-20";
export const COMMIT_HASH = "d8fd1ab";

export const FRONTEND_VERSION = APP_VERSION;

export function frontendDisplayShort() {
  return `v${APP_VERSION}`;
}

export function frontendDisplayFull(envShort = "dev") {
  return `v${APP_VERSION} · ${BUILD_LABEL} · ${envShort}`;
}

export function frontendBuildMetadata() {
  return {
    app_version: APP_VERSION,
    build_label: BUILD_LABEL,
    build_date: BUILD_DATE,
    commit: COMMIT_HASH,
    frontend_version: FRONTEND_VERSION,
  };
}
