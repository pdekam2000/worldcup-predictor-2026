/** Betting plan API — Phase A17 */

import { getAuthToken } from "@/api/authApi";
import { buildApiUrl } from "@/lib/config";

async function parseJson(response) {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = payload?.detail || payload?.message || `Request failed (${response.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return payload;
}

function authHeaders() {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function fetchBettingPlanToday({ bankroll, profile = "balanced" } = {}) {
  const params = new URLSearchParams();
  if (bankroll != null) params.set("bankroll", String(bankroll));
  if (profile) params.set("profile", profile);
  const qs = params.toString();
  const response = await fetch(buildApiUrl(`/api/betting-plan/today${qs ? `?${qs}` : ""}`), {
    headers: { ...authHeaders() },
  });
  return parseJson(response);
}

export async function fetchBettingPlanDate(date, { bankroll, profile = "balanced" } = {}) {
  const params = new URLSearchParams({ date });
  if (bankroll != null) params.set("bankroll", String(bankroll));
  if (profile) params.set("profile", profile);
  const response = await fetch(buildApiUrl(`/api/betting-plan/date?${params}`), {
    headers: { ...authHeaders() },
  });
  return parseJson(response);
}

export async function fetchBettingPortfolio({ date = "today", bankroll = 100, profile = "balanced" } = {}) {
  const params = new URLSearchParams({
    date,
    bankroll: String(bankroll),
    profile,
  });
  const response = await fetch(buildApiUrl(`/api/betting-plan/portfolio?${params}`), {
    headers: { ...authHeaders() },
  });
  return parseJson(response);
}

export async function fetchBettingCombo({ date = "today", type = "safe" } = {}) {
  const params = new URLSearchParams({ date, type });
  const response = await fetch(buildApiUrl(`/api/betting-plan/combo?${params}`), {
    headers: { ...authHeaders() },
  });
  return parseJson(response);
}
