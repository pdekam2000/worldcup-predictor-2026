/**
 * WorldCup Predictor auth API — FastAPI /api/auth/*
 */

import { AUTH_TOKEN_KEY, buildApiUrl } from "@/lib/config";

export function getAuthToken() {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAuthToken(token) {
  try {
    if (token) {
      localStorage.setItem(AUTH_TOKEN_KEY, token);
    } else {
      localStorage.removeItem(AUTH_TOKEN_KEY);
    }
  } catch {
    /* ignore */
  }
}

export function clearAuthToken() {
  setAuthToken(null);
}

async function parseJson(response) {
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
        : payload?.message || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return payload;
}

async function authFetch(path, { method = "GET", body } = {}) {
  const token = getAuthToken();
  const headers = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(buildApiUrl(path), {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return parseJson(response);
}

export async function login(email, password) {
  const payload = await authFetch("/api/auth/login", {
    method: "POST",
    body: { email, password },
  });
  if (payload?.access_token) {
    setAuthToken(payload.access_token);
  }
  return payload;
}

export async function register(email, password, inviteCode = null) {
  const body = { email, password };
  if (inviteCode) {
    body.invite_code = inviteCode;
  }
  const payload = await authFetch("/api/auth/register", {
    method: "POST",
    body,
  });
  if (payload?.access_token) {
    setAuthToken(payload.access_token);
  }
  return payload;
}

export async function fetchMe() {
  return authFetch("/api/auth/me");
}

export async function logout() {
  try {
    await authFetch("/api/auth/logout", { method: "POST" });
  } finally {
    clearAuthToken();
  }
}

export async function requestPasswordReset() {
  return authFetch("/api/auth/forgot-password", { method: "POST" });
}
