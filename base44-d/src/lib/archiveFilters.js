/** Archive list filters and client-side helpers (Phase 50.2). */

export const STATUS_FILTERS = [
  { id: "all", label: "All" },
  { id: "correct", label: "Correct" },
  { id: "wrong", label: "Wrong" },
  { id: "pending", label: "Pending" },
  { id: "partial", label: "Partial" },
];

export const SCOPE_TABS = [
  { id: "all", label: "All Predictions" },
  { id: "my", label: "My Predictions" },
  { id: "global", label: "Global Archive" },
];

export const MARKET_FILTERS = [
  { id: "all", label: "All markets" },
  { id: "1x2", label: "1X2" },
  { id: "btts", label: "BTTS" },
  { id: "over_under_2_5", label: "O/U 2.5" },
  { id: "correct_score", label: "Correct score" },
  { id: "first_goal_team", label: "First goal" },
  { id: "goal_minute", label: "Goal minute" },
];

export const SORT_OPTIONS = [
  { id: "newest", label: "Newest first" },
  { id: "oldest", label: "Oldest first" },
  { id: "match_date_desc", label: "Match date (newest)" },
  { id: "match_date_asc", label: "Match date (oldest)" },
];

export const SOURCE_BADGES = {
  my: { label: "Mine", className: "bg-primary/15 text-primary border-primary/30" },
  global_archive: { label: "System", className: "bg-blue-100 text-blue-700 border-blue-200" },
  system: { label: "System", className: "bg-blue-100 text-blue-700 border-blue-200" },
  legacy_import: { label: "Legacy", className: "bg-orange-100 text-orange-700 border-orange-200" },
  background_daily: { label: "Background", className: "bg-violet-100 text-violet-700 border-violet-200" },
};

const MARKET_LABELS = {
  "1x2": "1X2",
  btts: "BTTS",
  over_under_2_5: "O/U 2.5",
  correct_score: "CS",
  first_goal_team: "FG",
  goal_minute: "GM",
  double_chance: "DC",
  ht_result: "HT",
  goalscorer: "GS",
};

export function formatMarketKeys(keys) {
  if (!Array.isArray(keys) || keys.length === 0) return ["1X2"];
  return keys.map((k) => MARKET_LABELS[k] || String(k).replace(/_/g, " ").toUpperCase());
}

export function matchesTeamSearch(item, query) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    item?.home_team,
    item?.away_team,
    item?.match_name,
    item?.league,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(q);
}

export function matchesMarketFilter(item, marketId) {
  if (!marketId || marketId === "all") return true;
  const predicted = item?.predicted_market_keys;
  if (Array.isArray(predicted) && predicted.length > 0) {
    return predicted.includes(marketId);
  }
  if (marketId === "1x2") return true;
  return (item?.markets_count ?? 1) > 1;
}

export function filterArchiveItems(items, { search, marketFilter }) {
  return items.filter(
    (item) => matchesTeamSearch(item, search) && matchesMarketFilter(item, marketFilter)
  );
}

export function needsClientFiltering({ search, marketFilter }) {
  const hasSearch = Boolean(String(search || "").trim());
  const hasMarket = marketFilter && marketFilter !== "all";
  return hasSearch || hasMarket;
}
