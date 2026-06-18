/** App configuration — no Base44 runtime. */

const _envApiBase = import.meta.env.VITE_API_BASE_URL;

/** Empty string = same-origin API via Nginx (/api). Dev default only when unset in development. */
export const API_BASE =
  _envApiBase !== undefined
    ? _envApiBase
    : import.meta.env.DEV
      ? "http://127.0.0.1:8000"
      : "";

export const AUTH_TOKEN_KEY = "wcp_auth_token";

export function apiOrigin() {
  if (API_BASE) {
    return API_BASE.replace(/\/$/, "");
  }
  if (typeof window !== "undefined") {
    return window.location.origin;
  }
  return "";
}

export function buildApiUrl(path, params = {}) {
  const url = new URL(path.startsWith("/") ? path : `/${path}`, `${apiOrigin()}/`);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });
  return url.toString();
}
