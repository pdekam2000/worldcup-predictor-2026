/** AI Assistant API — Phase A19 */

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
  if (!token) throw new Error("Login required");
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

export async function fetchWatchlist() {
  const response = await fetch(buildApiUrl("/api/watchlist"), { headers: authHeaders() });
  return parseJson(response);
}

export async function addWatchlistItem(item) {
  const response = await fetch(buildApiUrl("/api/watchlist"), {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(item),
  });
  return parseJson(response);
}

export async function removeWatchlistItem(watchlistId) {
  const response = await fetch(buildApiUrl(`/api/watchlist/${watchlistId}`), {
    method: "DELETE",
    headers: authHeaders(),
  });
  return parseJson(response);
}

export async function fetchAssistantNotifications(category) {
  const qs = category ? `?category=${encodeURIComponent(category)}` : "";
  const response = await fetch(buildApiUrl(`/api/assistant/notifications${qs}`), { headers: authHeaders() });
  return parseJson(response);
}

export async function markAssistantNotificationRead(id) {
  const response = await fetch(buildApiUrl(`/api/assistant/notifications/${id}/read`), {
    method: "PATCH",
    headers: authHeaders(),
  });
  return parseJson(response);
}

export async function markAllAssistantNotificationsRead() {
  const response = await fetch(buildApiUrl("/api/assistant/notifications/read-all"), {
    method: "POST",
    headers: authHeaders(),
  });
  return parseJson(response);
}

export async function fetchAssistantPreferences() {
  const response = await fetch(buildApiUrl("/api/preferences"), { headers: authHeaders() });
  return parseJson(response);
}

export async function updateAssistantPreferences(prefs) {
  const response = await fetch(buildApiUrl("/api/preferences"), {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(prefs),
  });
  return parseJson(response);
}

export async function fetchDailyBriefing(date) {
  const qs = date ? `?date=${encodeURIComponent(date)}` : "";
  const response = await fetch(buildApiUrl(`/api/daily-briefing${qs}`), { headers: authHeaders() });
  return parseJson(response);
}

export async function fetchWeeklyInsights() {
  const response = await fetch(buildApiUrl("/api/assistant/weekly-insights"), { headers: authHeaders() });
  return parseJson(response);
}
