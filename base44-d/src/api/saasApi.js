/**
 * Authenticated SaaS API — settings, favorites, alerts, notifications, history, subscription, admin.
 */

import { getAuthToken } from "@/api/authApi";
import { adminGateHeaders, superAdminGateHeaders } from "@/lib/adminGate";
import { buildApiUrl } from "@/lib/config";
import { extractApiErrorMessage } from "@/lib/apiError";

async function parseJson(response) {
  let payload;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new Error(extractApiErrorMessage(payload, response.status));
  }
  return payload;
}

async function saasFetch(path, { method = "GET", body, adminGate = false, superAdminGate = false } = {}) {
  const token = getAuthToken();
  const headers = {
    Accept: "application/json",
    ...(adminGate ? adminGateHeaders() : {}),
    ...(superAdminGate ? superAdminGateHeaders() : {}),
  };
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

export async function fetchBillingReadiness() {
  return saasFetch("/api/billing/readiness");
}

export async function createCheckoutSession(plan) {
  return saasFetch("/api/billing/create-checkout-session", { method: "POST", body: { plan } });
}

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

export async function fetchPerformanceSummary(competition = "world_cup_2026") {
  const qs = new URLSearchParams({ competition });
  return saasFetch(`/api/performance/summary?${qs}`);
}

export async function fetchBestTips({ competition = "world_cup_2026", limit = 12 } = {}) {
  const qs = new URLSearchParams({ competition, limit: String(limit) });
  return saasFetch(`/api/best-tips?${qs}`);
}

export async function fetchUnifiedEngineStatus() {
  return saasFetch("/api/unified/status");
}

export async function fetchUnifiedPrediction(fixtureId, { competition, compare = false } = {}) {
  const qs = new URLSearchParams();
  if (competition) qs.set("competition", competition);
  if (compare) qs.set("compare", "true");
  const suffix = qs.toString() ? `?${qs}` : "";
  return saasFetch(`/api/unified/predict/${fixtureId}${suffix}`, { adminGate: true });
}

export async function fetchUnifiedBacktestSummary({ limit = 200, competition = "world_cup_2026" } = {}) {
  const qs = new URLSearchParams({ limit: String(limit), competition });
  return saasFetch(`/api/unified/backtest/summary?${qs}`, { adminGate: true });
}

export async function fetchHistoryArchive({
  limit = 50,
  offset = 0,
  resultFilter = "all",
  scope = "all",
  sort = "newest",
  competition = "all",
} = {}) {
  const qs = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    result_filter: resultFilter,
    scope,
    sort,
    competition,
  });
  return saasFetch(`/api/history?${qs}`);
}

export async function fetchEvaluatedResults({
  range = "all",
  status = "all",
  market = "best_bets",
  limit = 100,
  offset = 0,
  competition = "all",
  utcOffsetMinutes = null,
} = {}) {
  const qs = new URLSearchParams({
    range,
    status,
    market,
    limit: String(limit),
    offset: String(offset),
    competition,
  });
  if (utcOffsetMinutes != null && !Number.isNaN(Number(utcOffsetMinutes))) {
    qs.set("utc_offset_minutes", String(utcOffsetMinutes));
  }
  return saasFetch(`/api/results/evaluated?${qs}`);
}

export async function fetchPredictionHistoryEntry(entryId) {
  return saasFetch(`/api/history/${encodeURIComponent(entryId)}`);
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

export async function fetchAdminUserUsage(userId) {
  return saasFetch(`/api/admin/users/${userId}/usage`, { adminGate: true });
}

export async function resetAdminUserQuota(userId) {
  return saasFetch(`/api/admin/users/${userId}/quota/reset`, { method: "POST", adminGate: true });
}

export async function updateAdminUserRole(userId, role, confirmSelf = false) {
  return saasFetch(`/api/admin/users/${userId}/role`, {
    method: "PATCH",
    body: { role, confirm_self: confirmSelf },
    superAdminGate: true,
  });
}

export async function updateAdminUserPlan(userId, plan) {
  const qs = new URLSearchParams({ plan });
  return saasFetch(`/api/admin/users/${userId}/subscription?${qs.toString()}`, {
    method: "PATCH",
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

export async function fetchAdminUserBilling(userId) {
  return saasFetch(`/api/admin/users/${userId}/billing`, { superAdminGate: true });
}

export async function fetchCommercialAnalytics() {
  return saasFetch("/api/admin/commercial/analytics", { superAdminGate: true });
}

export async function fetchCommercialReadiness() {
  return saasFetch("/api/admin/commercial/readiness", { superAdminGate: true });
}

export async function fetchAdminAccuracyEvaluations(params = {}) {
  const qs = new URLSearchParams({
    competition: params.competition || "world_cup_2026",
    status: params.status || "all",
    pick_tier: params.pick_tier || "all",
    limit: String(params.limit ?? 50),
    offset: String(params.offset ?? 0),
  });
  return saasFetch(`/api/admin/accuracy/evaluations?${qs}`, { adminGate: true });
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

/** Phase 59A — Elite Shadow admin preview (shadow JSONL only) */
export async function fetchAdminEliteShadowSummary() {
  return saasFetch("/api/admin/elite-shadow/summary", { superAdminGate: true });
}

/** Phase A22 — Elite Shadow scheduler health */
export async function fetchAdminEliteShadowHealth() {
  return saasFetch("/api/admin/elite-shadow/health", { superAdminGate: true });
}

/** Phase A22 — Elite Shadow admin maintenance action */
export async function postAdminEliteShadowAction(action, params = {}) {
  const qs = new URLSearchParams();
  if (params.force) qs.set("force", "true");
  if (params.dry_run) qs.set("dry_run", "true");
  const suffix = qs.toString() ? `?${qs}` : "";
  return saasFetch(`/api/admin/elite-shadow/actions/${encodeURIComponent(action)}${suffix}`, {
    method: "POST",
    superAdminGate: true,
  });
}

export async function fetchAdminEliteShadowPredictions(params = {}) {
  const qs = new URLSearchParams({
    market: params.market || "all",
    tier: params.tier || "all",
    status: params.status || "all",
    limit: String(params.limit ?? 50),
    offset: String(params.offset ?? 0),
  });
  return saasFetch(`/api/admin/elite-shadow/predictions?${qs}`, { superAdminGate: true });
}

export async function fetchAdminEliteShadowFixture(fixtureId) {
  return saasFetch(`/api/admin/elite-shadow/predictions/${encodeURIComponent(fixtureId)}`, { superAdminGate: true });
}

export async function fetchAdminEliteShadowEvaluations(params = {}) {
  const qs = new URLSearchParams({
    outcome: params.outcome || "all",
    market: params.market || "all",
    limit: String(params.limit ?? 100),
    offset: String(params.offset ?? 0),
  });
  return saasFetch(`/api/admin/elite-shadow/evaluations?${qs}`, { superAdminGate: true });
}

export async function fetchAdminEliteShadowRootCause(params = {}) {
  const qs = new URLSearchParams({
    market: params.market || "all",
    limit: String(params.limit ?? 100),
    offset: String(params.offset ?? 0),
  });
  if (params.fixture_id != null) qs.set("fixture_id", String(params.fixture_id));
  return saasFetch(`/api/admin/elite-shadow/root-cause?${qs}`, { superAdminGate: true });
}

/** Phase 59C — Shadow vs production comparison (super_admin only) */
export async function fetchAdminEliteShadowComparison(params = {}) {
  const qs = new URLSearchParams({
    market: params.market || "all",
    tier: params.tier || "all",
    status: params.status || "all",
    disagreement_only: String(Boolean(params.disagreement_only)),
    limit: String(params.limit ?? 200),
    offset: String(params.offset ?? 0),
  });
  if (params.fixture_id != null && params.fixture_id !== "") {
    qs.set("fixture_id", String(params.fixture_id));
  }
  return saasFetch(`/api/admin/elite-shadow/comparison?${qs}`, { superAdminGate: true });
}

/** Phase 60D — Elite World Cup experimental predictions */
export async function fetchEliteWorldCupPredictions(params = {}) {
  const qs = new URLSearchParams({
    market: params.market || "all",
    tier: params.tier || "all",
    status: params.status || "all",
    limit: String(params.limit ?? 50),
    offset: String(params.offset ?? 0),
  });
  return saasFetch(`/api/elite/world-cup/predictions?${qs}`, { superAdminGate: true });
}

/** Phase 61 — Admin autonomous performance certification */
export async function fetchAdminPerformanceCertification() {
  return saasFetch("/api/admin/performance/certification", { superAdminGate: true });
}

/** Phase 63 — Owner command center */
export async function fetchOwnerOverview() {
  return saasFetch("/api/owner/overview");
}

export async function fetchOwnerMonitoring() {
  return saasFetch("/api/owner/monitoring");
}

export async function fetchOwnerAutonomousStatus() {
  return saasFetch("/api/owner/autonomous/status");
}

export async function fetchOwnerNotifications() {
  return saasFetch("/api/owner/notifications");
}

export async function ownerRunAutonomousOnce({ dryRun = false, fixtureLimit = 10 } = {}) {
  return saasFetch("/api/owner/autonomous/run-once", {
    method: "POST",
    body: { dry_run: dryRun, fixture_limit: fixtureLimit },
  });
}

export async function fetchOwnerModelCenter() {
  return saasFetch("/api/owner/model-center");
}

export async function fetchOwnerPerformanceCenter() {
  return saasFetch("/api/owner/performance-center");
}

export async function fetchOwnerHealthDashboard() {
  return saasFetch("/api/owner/health-dashboard");
}

export async function fetchOwnerResearchLab({ refresh = false } = {}) {
  const qs = refresh ? "?refresh=true" : "";
  return saasFetch(`/api/owner/research-lab${qs}`);
}

export async function fetchOwnerResearchLabSummary({ refresh = false } = {}) {
  const qs = refresh ? "?refresh=true" : "";
  return saasFetch(`/api/owner/research-lab/summary${qs}`);
}

export async function fetchOwnerPromotionStatus() {
  return saasFetch("/api/owner/promotion/status");
}

export async function fetchOwnerBettingIntelligence() {
  return saasFetch("/api/owner/betting-intelligence");
}

export async function ownerRunAutonomousEvaluation() {
  return saasFetch("/api/owner/autonomous/evaluation", { method: "POST" });
}

export async function ownerRunAutonomousCertification() {
  return saasFetch("/api/owner/autonomous/certification", { method: "POST" });
}

export async function ownerEnableScheduler() {
  return saasFetch("/api/owner/autonomous/enable-scheduler", { method: "POST" });
}

export async function ownerDisableScheduler() {
  return saasFetch("/api/owner/autonomous/disable-scheduler", { method: "POST" });
}

export async function fetchOwnerPrefetchCoverage(windowDays = 7) {
  const qs = new URLSearchParams({ window_days: String(windowDays) });
  return saasFetch(`/api/owner/prefetch/coverage?${qs}`);
}

export async function runOwnerPrefetchOnce({ windowDays = 7, maxPerCycle = 24 } = {}) {
  const qs = new URLSearchParams({
    window_days: String(windowDays),
    max_per_cycle: String(maxPerCycle),
  });
  return saasFetch(`/api/owner/prefetch/run-once?${qs}`, { method: "POST" });
}

/** Phase ECSE-X2-M8 — Owner ECSE shadow lab (research only) */
export async function fetchOwnerEcseShadowLabSummary() {
  return saasFetch("/api/owner/ecse-shadow-lab/summary");
}

export async function fetchOwnerEcseShadowLabFixtures({
  filter = "all",
  league,
  dateFrom,
  dateTo,
  limit = 100,
  offset = 0,
} = {}) {
  const qs = new URLSearchParams({
    filter,
    limit: String(limit),
    offset: String(offset),
  });
  if (league) qs.set("league", league);
  if (dateFrom) qs.set("date_from", dateFrom);
  if (dateTo) qs.set("date_to", dateTo);
  return saasFetch(`/api/owner/ecse-shadow-lab/fixtures?${qs}`);
}

export async function fetchOwnerEcseShadowLabFixture(fixtureId) {
  return saasFetch(`/api/owner/ecse-shadow-lab/fixtures/${encodeURIComponent(fixtureId)}`);
}

/** Phase ECSE-ODDALERTS-3 — Owner OddAlerts ECSE shadow lab (research only) */
export async function fetchOwnerEcseOddalertsShadow(params = {}) {
  const qs = new URLSearchParams();
  const map = {
    shadowRunId: "shadow_run_id",
    dateFrom: "date_from",
    dateTo: "date_to",
    competition: "competition",
    team: "team",
    promotionAction: "promotion_action",
    status: "status",
    top1Score: "top1_score",
    top1Outcome: "top1_outcome",
    lambdaHomeMin: "lambda_home_min",
    lambdaHomeMax: "lambda_home_max",
    lambdaAwayMin: "lambda_away_min",
    lambdaAwayMax: "lambda_away_max",
    top3ContainsActual: "top3_contains_actual",
    top5ContainsActual: "top5_contains_actual",
    bookmakerAgreementMin: "bookmaker_agreement_min",
    crosswalkConfidenceMin: "crosswalk_confidence_min",
    segmentRecommendation: "segment_recommendation",
    limit: "limit",
    offset: "offset",
  };
  for (const [key, param] of Object.entries(map)) {
    const val = params[key];
    if (val !== undefined && val !== null && val !== "") {
      qs.set(param, String(val));
    }
  }
  return saasFetch(`/api/owner/ecse-oddalerts-shadow?${qs}`);
}

/** Phase ECSE-ODDALERTS-5 — Live shadow monitor (owner only) */
export async function fetchOwnerEcseOddalertsShadowMonitor(params = {}) {
  const qs = new URLSearchParams();
  if (params.dateFrom) qs.set("date_from", params.dateFrom);
  if (params.dateTo) qs.set("date_to", params.dateTo);
  if (params.status) qs.set("status", params.status);
  if (params.limit) qs.set("limit", String(params.limit));
  return saasFetch(`/api/owner/ecse-oddalerts-shadow/monitor?${qs}`);
}

export async function fetchPredOpsCoverage() {
  return saasFetch("/api/predops/coverage");
}

export async function fetchPredOpsCoverageAdmin() {
  return saasFetch("/api/predops/coverage/admin");
}

export async function fetchPredOpsQueue() {
  return saasFetch("/api/predops/queue");
}

export async function fetchPredOpsComboReadiness() {
  return saasFetch("/api/predops/combo-readiness");
}

export async function fetchPredOpsSnapshotLatest(fixtureId) {
  return saasFetch(`/api/predops/snapshots/latest?fixture_id=${encodeURIComponent(fixtureId)}`);
}

export async function runPredOpsOnce({ windowDays = 7, maxJobs = 12, dryRun = false } = {}) {
  const qs = new URLSearchParams({
    window_days: String(windowDays),
    max_jobs: String(maxJobs),
    dry_run: dryRun ? "true" : "false",
  });
  return saasFetch(`/api/predops/run-once?${qs}`, { method: "POST" });
}

/** Phase 51 — Elite Goal Timing engine */
export async function fetchGoalTimingStatus() {
  return saasFetch("/api/goal-timing/status");
}

export async function fetchGoalTimingDashboard() {
  return saasFetch("/api/goal-timing/dashboard");
}

export async function fetchGoalTimingPicks({ limit = 20 } = {}) {
  const qs = new URLSearchParams({ limit: String(limit) });
  return saasFetch(`/api/goal-timing/picks?${qs}`);
}

export async function fetchGoalTimingPrediction(fixtureId) {
  return saasFetch(`/api/goal-timing/predictions/${encodeURIComponent(fixtureId)}`);
}

export async function fetchGoalTimingHistory({ limit = 50, offset = 0, competitionKey } = {}) {
  const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (competitionKey) qs.set("competition_key", competitionKey);
  return saasFetch(`/api/goal-timing/history?${qs}`);
}

export async function fetchGoalTimingAccuracy({ competitionKey } = {}) {
  const qs = new URLSearchParams();
  if (competitionKey) qs.set("competition_key", competitionKey);
  const suffix = qs.toString() ? `?${qs}` : "";
  return saasFetch(`/api/goal-timing/accuracy${suffix}`);
}

export async function fetchGoalTimingPerformance({ competitionKey } = {}) {
  const qs = new URLSearchParams();
  if (competitionKey) qs.set("competition_key", competitionKey);
  const suffix = qs.toString() ? `?${qs}` : "";
  return saasFetch(`/api/goal-timing/performance${suffix}`);
}
