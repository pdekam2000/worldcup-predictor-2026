/** Human-readable labels for specialist status_reason codes. */

export const SPECIALIST_REASON_LABELS = {
  provider_not_configured: "Provider not configured",
  data_not_published_yet: "Data not published yet",
  live_data_available: "Live data available",
  heuristic_partial: "Partial heuristic data",
  missing_league_id: "League ID missing",
  missing_required_fixture_fields: "Missing fixture fields",
  cache_hit: "Served from cache",
};

export function labelForStatusReason(reason) {
  if (!reason) return null;
  return SPECIALIST_REASON_LABELS[reason] || reason.replace(/_/g, " ");
}
