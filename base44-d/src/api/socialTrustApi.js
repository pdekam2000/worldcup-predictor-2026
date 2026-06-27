/** Social sharing & public trust API — Phase A20 */

import { getAuthToken } from "@/api/authApi";
import { buildApiUrl } from "@/lib/config";

async function parseJson(response) {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = payload?.detail?.message || payload?.detail || payload?.message || `Request failed (${response.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return payload;
}

function authHeaders() {
  const token = getAuthToken();
  if (!token) throw new Error("Login required to create share links");
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

export async function createPickShare(data) {
  const response = await fetch(buildApiUrl("/api/share/pick"), {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return parseJson(response);
}

export async function createComboShare(data) {
  const response = await fetch(buildApiUrl("/api/share/combo"), {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return parseJson(response);
}

export async function createPlanShare(data) {
  const response = await fetch(buildApiUrl("/api/share/betting-plan"), {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return parseJson(response);
}

export async function createPaperReportShare(data) {
  const response = await fetch(buildApiUrl("/api/share/paper-report"), {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return parseJson(response);
}

export async function fetchSharePick(id) {
  const response = await fetch(buildApiUrl(`/api/share/pick/${id}`));
  return parseJson(response);
}

export async function fetchShareCombo(id) {
  const response = await fetch(buildApiUrl(`/api/share/combo/${id}`));
  return parseJson(response);
}

export async function fetchSharePlan(id) {
  const response = await fetch(buildApiUrl(`/api/share/plan/${id}`));
  return parseJson(response);
}

export async function fetchSharePaperReport(id) {
  const response = await fetch(buildApiUrl(`/api/share/paper-report/${id}`));
  return parseJson(response);
}

export async function fetchPublicAccuracy() {
  const response = await fetch(buildApiUrl("/api/public/accuracy"));
  return parseJson(response);
}

export function absoluteShareUrl(path) {
  if (typeof window !== "undefined") {
    return `${window.location.origin}${path}`;
  }
  return path;
}
