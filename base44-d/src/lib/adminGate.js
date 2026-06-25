/**
 * Phase 37A — admin gate session tokens (sessionStorage only; cleared on tab close).
 * Keys are verified server-side; tokens are never the raw access key.
 */

import { getAuthToken } from "@/api/authApi";
import { buildApiUrl } from "@/lib/config";

const ADMIN_GATE_KEY = "wcp_admin_gate_token";
const SUPER_ADMIN_GATE_KEY = "wcp_super_admin_gate_token";

export function getAdminGateToken() {
  try {
    return sessionStorage.getItem(ADMIN_GATE_KEY) || "";
  } catch {
    return "";
  }
}

export function getSuperAdminGateToken() {
  try {
    return sessionStorage.getItem(SUPER_ADMIN_GATE_KEY) || "";
  } catch {
    return "";
  }
}

export function setAdminGateToken(token) {
  try {
    if (token) sessionStorage.setItem(ADMIN_GATE_KEY, token);
    else sessionStorage.removeItem(ADMIN_GATE_KEY);
  } catch {
    /* ignore */
  }
}

export function setSuperAdminGateToken(token) {
  try {
    if (token) sessionStorage.setItem(SUPER_ADMIN_GATE_KEY, token);
    else sessionStorage.removeItem(SUPER_ADMIN_GATE_KEY);
  } catch {
    /* ignore */
  }
}

export function clearAdminGateTokens() {
  setAdminGateToken("");
  setSuperAdminGateToken("");
}

async function gateFetch(path, { method = "GET", body, gateHeader, gateToken } = {}) {
  const token = getAuthToken();
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  if (gateToken && gateHeader) headers[gateHeader] = gateToken;
  const response = await fetch(buildApiUrl(path), {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message || payload?.message || "Access denied.";
    const err = new Error(message);
    err.status = response.status;
    err.detail = detail;
    throw err;
  }
  return payload;
}

export async function fetchAdminGateStatus() {
  return gateFetch("/api/admin/gate/status", {
    gateHeader: "X-Admin-Gate-Token",
    gateToken: getAdminGateToken(),
  });
}

export async function verifyAdminGate(accessKey) {
  const payload = await gateFetch("/api/admin/gate/verify", {
    method: "POST",
    body: { access_key: accessKey },
  });
  if (payload?.gate_token) setAdminGateToken(payload.gate_token);
  return payload;
}

export async function fetchSuperAdminGateStatus() {
  return gateFetch("/api/admin/gate/super-admin/status", {
    gateHeader: "X-Super-Admin-Gate-Token",
    gateToken: getSuperAdminGateToken(),
  });
}

export async function verifySuperAdminGate(accessKey) {
  const payload = await gateFetch("/api/admin/gate/super-admin/verify", {
    method: "POST",
    body: { access_key: accessKey },
  });
  if (payload?.gate_token) setSuperAdminGateToken(payload.gate_token);
  return payload;
}

export function adminGateHeaders() {
  const token = getAdminGateToken();
  return token ? { "X-Admin-Gate-Token": token } : {};
}

export function superAdminGateHeaders() {
  const token = getSuperAdminGateToken();
  return token ? { "X-Super-Admin-Gate-Token": token } : {};
}
