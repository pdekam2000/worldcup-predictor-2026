/**
 * Authenticated SaaS API — settings, favorites, alerts, notifications, history, subscription, admin.
 */

import { getAuthToken } from "@/api/authApi";
import { buildApiUrl } from "@/lib/config";

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

async function saasFetch(path, { method = "GET", body } = {}) {
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

export async function fetchDashboard() {
  return saasFetch("/api/user/dashboard");
}

export async function fetchSettings() {
  return saasFetch("/api/user/settings");
}

export async function updateSettings(patch) {
  return saasFetch("/api/user/settings", { method: "PATCH", body: patch });
}

export async function fetchFavorites() {
  return saasFetch("/api/user/favorites");
}

export async function addFavorite(favorite) {
  return saasFetch("/api/user/favorites", { method: "POST", body: favorite });
}

export async function removeFavorite(favoriteId) {
  return saasFetch(`/api/user/favorites/${favoriteId}`, { method: "DELETE" });
}

export async function fetchAlerts() {
  return saasFetch("/api/user/alerts");
}

export async function markAlertRead(alertId) {
  return saasFetch(`/api/user/alerts/${alertId}/read`, { method: "PATCH" });
}

export async function markAllAlertsRead() {
  return saasFetch("/api/user/alerts/read-all", { method: "POST" });
}

export async function fetchNotifications() {
  return saasFetch("/api/user/notifications");
}

export async function markNotificationRead(notificationId) {
  return saasFetch(`/api/user/notifications/${notificationId}/read`, { method: "PATCH" });
}

export async function markAllNotificationsRead() {
  return saasFetch("/api/user/notifications/read-all", { method: "POST" });
}

export async function fetchPredictionHistoryPage({ limit = 50, offset = 0 } = {}) {
  const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return saasFetch(`/api/user/prediction-history?${qs}`);
}

export async function fetchSubscription() {
  return saasFetch("/api/user/subscription");
}

export async function fetchAdminStats() {
  return saasFetch("/api/admin/stats");
}

export async function fetchAdminUsers({ search = "", limit = 50, offset = 0 } = {}) {
  const qs = new URLSearchParams({ search, limit: String(limit), offset: String(offset) });
  return saasFetch(`/api/admin/users?${qs.toString()}`);
}

export async function fetchAdminHealth() {
  return saasFetch("/api/admin/health");
}

export async function updateAdminUserRole(userId, role) {
  return saasFetch(`/api/admin/users/${userId}/role`, { method: "PATCH", body: { role } });
}

export async function updateAdminUserPlan(userId, plan) {
  const qs = new URLSearchParams({ plan });
  return saasFetch(`/api/admin/users/${userId}/subscription?${qs.toString()}`, { method: "PATCH" });
}
