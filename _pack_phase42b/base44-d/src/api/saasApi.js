/**
 * Authenticated SaaS API — settings, favorites, alerts, notifications, history, subscription, admin.
 */

import { getAuthToken } from "@/api/authApi";
import { adminGateHeaders, superAdminGateHeaders } from "@/lib/adminGate";
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

async function saasFetch(path, { method = "GET", body, adminGate = false, superAdminGate = false } = {}) {
  const token = getAuthToken();
  const headers = { Accept: "application/json", ...(adminGate ? adminGateHeaders() : {}), ...(superAdminGate ? superAdminGateHeaders() : {}) };
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

export async function fetchAccuracySummary(competition = "world_cup_2026") {
  const qs = new URLSearchParams({ competition });
  return saasFetch(`/api/accuracy/summary?${qs}`);
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

export async function fetchPredictionHistoryPage({ limit = 50, offset = 0, resultFilter = "all" } = {}) {
  const qs = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    result_filter: resultFilter,
  });
  return saasFetch(`/api/user/prediction-history?${qs}`);
}

export async function fetchPredictionHistoryResults({ limit = 50, offset = 0, resultFilter = "all" } = {}) {
  const qs = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    result_filter: resultFilter,
  });
  return saasFetch(`/api/user/prediction-history/results?${qs}`);
}

export async function fetchSubscription() {
  return saasFetch("/api/user/subscription");
}

export async function fetchUserQuota() {
  return saasFetch("/api/user/quota");
}

export async function contactAdmin({ subject, message, category = "other" }) {
  return saasFetch("/api/user/contact-admin", { method: "POST", body: { subject, message, category } });
}

/** Phase 39B-1/39B-2 — billing readiness + checkout session. */
export async function fetchBillingReadiness() {
  return saasFetch("/api/billing/readiness");
}

export async function createCheckoutSession(plan) {
  return saasFetch("/api/billing/create-checkout-session", {
    method: "POST",
    body: { plan },
  });
}

/** Phase 39B-4 — billing status, history, customer portal. */
export async function fetchBillingStatus() {
  return saasFetch("/api/billing/status");
}

export async function fetchBillingHistory({ limit = 50, offset = 0 } = {}) {
  const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return saasFetch(`/api/billing/history?${qs}`);
}

export async function createCustomerPortalSession(returnUrl) {
  return saasFetch("/api/billing/customer-portal", {
    method: "POST",
    body: returnUrl ? { return_url: returnUrl } : {},
  });
}

export async function fetchAdminUserBilling(userId) {
  return saasFetch(`/api/admin/users/${userId}/billing`, { superAdminGate: true });
}

export async function fetchAdminAccuracyEvaluations({
  competition = "world_cup_2026",
  status = "all",
  pick_tier = "all",
  confidence_min,
  confidence_max,
  limit = 50,
  offset = 0,
} = {}) {
  const qs = new URLSearchParams({
    competition,
    status,
    pick_tier,
    limit: String(limit),
    offset: String(offset),
  });
  if (confidence_min != null) qs.set("confidence_min", String(confidence_min));
  if (confidence_max != null) qs.set("confidence_max", String(confidence_max));
  return saasFetch(`/api/admin/accuracy/evaluations?${qs}`, { adminGate: true });
}

export async function fetchAdminFixtureInspector(fixtureId) {
  return saasFetch(`/api/admin/accuracy/fixtures/${fixtureId}`, { adminGate: true });
}

export async function rebuildAdminAccuracy({ competition = "world_cup_2026", evaluate = false } = {}) {
  const qs = new URLSearchParams({ competition, evaluate: String(evaluate) });
  return saasFetch(`/api/admin/accuracy/rebuild?${qs}`, { method: "POST", adminGate: true });
}

export async function fetchAdminLearningDashboard(competition = "world_cup_2026") {
  return saasFetch(`/api/admin/learning/dashboard?competition=${competition}`, { adminGate: true });
}

export async function fetchAdminLearningOptimization(competition = "world_cup_2026") {
  return saasFetch(`/api/admin/learning/optimization?competition=${competition}`, { adminGate: true });
}

export async function generateAdminLearningReport(competition = "world_cup_2026", version = "v2") {
  const qs = new URLSearchParams({ competition, version });
  return saasFetch(`/api/admin/learning/reports/generate?${qs}`, { method: "POST", adminGate: true });
}

export async function fetchAdminLearningReports({ competition = "world_cup_2026", limit = 20 } = {}) {
  const qs = new URLSearchParams({ competition, limit: String(limit) });
  return saasFetch(`/api/admin/learning/reports?${qs}`, { adminGate: true });
}

export async function fetchAdminAccuracyAudit(competition = "world_cup_2026") {
  return saasFetch(`/api/admin/accuracy/audit?competition=${competition}`, { adminGate: true });
}

export async function fetchAdminStats() {
  return saasFetch("/api/admin/stats", { adminGate: true });
}

export async function fetchAdminUsers({ search = "", limit = 50, offset = 0 } = {}) {
  const qs = new URLSearchParams({ search, limit: String(limit), offset: String(offset) });
  return saasFetch(`/api/admin/users?${qs.toString()}`, { adminGate: true });
}

export async function fetchAdminHealth() {
  return saasFetch("/api/admin/health", { adminGate: true });
}

export async function fetchAdminQuota() {
  return saasFetch("/api/admin/quota", { adminGate: true });
}

export async function updateAdminUserRole(userId, role, confirmSelf = false) {
  return saasFetch(`/api/admin/users/${userId}/role`, {
    method: "PATCH",
    body: { role, confirm_self: confirmSelf },
    superAdminGate: true,
  });
}

export async function banAdminUser(userId, reason = "", confirmSelf = false) {
  return saasFetch(`/api/admin/users/${userId}/ban`, {
    method: "POST",
    body: { reason, confirm_self: confirmSelf },
    superAdminGate: true,
  });
}

export async function unbanAdminUser(userId) {
  return saasFetch(`/api/admin/users/${userId}/unban`, { method: "POST", superAdminGate: true });
}

export async function kickAdminUser(userId) {
  return saasFetch(`/api/admin/users/${userId}/kick`, { method: "POST", superAdminGate: true });
}

export async function updateAdminUserPlan(userId, plan) {
  const qs = new URLSearchParams({ plan });
  return saasFetch(`/api/admin/users/${userId}/subscription?${qs.toString()}`, { method: "PATCH", superAdminGate: true });
}

export async function fetchAdminUserUsage(userId) {
  return saasFetch(`/api/admin/users/${userId}/usage`, { adminGate: true });
}

export async function resetAdminUserQuota(userId) {
  return saasFetch(`/api/admin/users/${userId}/quota/reset`, { method: "POST", adminGate: true });
}

export async function fetchCommercialAnalytics() {
  return saasFetch("/api/admin/commercial/analytics", { superAdminGate: true });
}

export async function fetchCommercialReadiness() {
  return saasFetch("/api/admin/commercial/readiness", { superAdminGate: true });
}
