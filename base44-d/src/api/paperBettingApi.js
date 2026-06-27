/** Paper betting API — Phase A18 */

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
  if (!token) throw new Error("Login required for paper betting");
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

export async function fetchPaperAccount() {
  const response = await fetch(buildApiUrl("/api/paper-betting/account"), { headers: authHeaders() });
  return parseJson(response);
}

export async function createPaperAccount({ starting_bankroll, currency = "EUR", risk_profile = "balanced", reset_month = false }) {
  const response = await fetch(buildApiUrl("/api/paper-betting/account"), {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ starting_bankroll, currency, risk_profile, reset_month }),
  });
  return parseJson(response);
}

export async function placePaperBet(bet) {
  const response = await fetch(buildApiUrl("/api/paper-betting/bets"), {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(bet),
  });
  return parseJson(response);
}

export async function placePaperCombo({ legs, combo_type, source_page }) {
  const response = await fetch(buildApiUrl("/api/paper-betting/bets/combo"), {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ legs, combo_type, source_page }),
  });
  return parseJson(response);
}

export async function fetchPaperBets(status) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  const response = await fetch(buildApiUrl(`/api/paper-betting/bets${qs}`), { headers: authHeaders() });
  return parseJson(response);
}

export async function fetchPaperSummary(period = "all") {
  const response = await fetch(buildApiUrl(`/api/paper-betting/summary?period=${period}`), { headers: authHeaders() });
  return parseJson(response);
}

export async function settlePaperBets() {
  const response = await fetch(buildApiUrl("/api/paper-betting/settle"), { method: "POST", headers: authHeaders() });
  return parseJson(response);
}

export async function fetchPaperMonthlyReport(month) {
  const qs = month ? `?month=${encodeURIComponent(month)}` : "";
  const response = await fetch(buildApiUrl(`/api/paper-betting/monthly-report${qs}`), { headers: authHeaders() });
  return parseJson(response);
}

export async function fetchPaperStrategyComparison(bankroll = 100) {
  const response = await fetch(buildApiUrl(`/api/paper-betting/strategy-comparison?bankroll=${bankroll}`), {
    headers: authHeaders(),
  });
  return parseJson(response);
}
