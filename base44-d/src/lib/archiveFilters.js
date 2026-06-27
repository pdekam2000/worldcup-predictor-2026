/** Archive list filters and client-side helpers (Phase 50.2). */

export const STATUS_FILTERS = [
  { id: "all", label: "All" },
  { id: "evaluated", label: "Evaluated" },
  { id: "correct", label: "Correct" },
  { id: "wrong", label: "Wrong" },
  { id: "partial", label: "Partial" },
  { id: "pending", label: "Pending" },
];

export const DATE_QUICK_FILTERS = [
  { id: "all", label: "All dates" },
  { id: "yesterday", label: "Yesterday" },
  { id: "7d", label: "Last 7 days" },
  { id: "30d", label: "Last 30 days" },
];

export const SCOPE_TABS = [
  { id: "all", label: "All Predictions" },
  { id: "my", label: "My Predictions" },
  { id: "global", label: "Global Archive" },
];

export const MARKET_FILTERS = [
  { id: "best_bets", label: "Best Bets Only" },
  { id: "all", label: "All Markets" },
  { id: "1x2", label: "1X2" },
  { id: "btts", label: "BTTS" },
  { id: "over_2_5", label: "Over 2.5" },
  { id: "under_2_5", label: "Under 2.5" },
  { id: "over_under_2_5", label: "O/U 2.5" },
  { id: "double_chance", label: "Double Chance" },
  { id: "correct_score", label: "Correct Score" },
  { id: "first_goal_team", label: "First Goal Team" },
  { id: "goal_minute", label: "Goal Time Range" },
  { id: "goalscorer", label: "Goalscorer" },
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
  if (marketId === "best_bets") {
    if (item?.has_best_bet) return true;
    const rows = item?.market_breakdown || [];
    return rows.some((r) => r.was_best_bet && r.was_user_visible);
  }
  const rows = item?.market_breakdown || [];
  const keys = new Set(rows.map((r) => r.market_key));
  if (marketId === "over_2_5" || marketId === "under_2_5") {
    if (!keys.has("over_under_2_5")) return false;
    const row = rows.find((r) => r.market_key === "over_under_2_5");
    const pick = String(row?.predicted_pick || "").toLowerCase();
    if (marketId === "over_2_5") return pick.includes("over");
    return pick.includes("under");
  }
  if (keys.has(marketId)) return true;
  const predicted = item?.predicted_market_keys;
  if (Array.isArray(predicted) && predicted.includes(marketId)) return true;
  if (marketId === "1x2") return true;
  return false;
}

export function filterArchiveItems(items, { search, marketFilter }) {
  return items.filter(
    (item) => matchesTeamSearch(item, search) && matchesMarketFilter(item, marketFilter)
  );
}

export function marketViewForItem(item, marketId) {
  if (!item || !marketId || marketId === "all") return null;
  const rows = item.market_breakdown || [];
  if (marketId === "best_bets") {
    return rows.find((r) => r.was_best_bet) || null;
  }
  const key = marketId === "over_2_5" || marketId === "under_2_5" ? "over_under_2_5" : marketId;
  const row = rows.find((r) => r.market_key === key);
  if (!row) return null;
  if (marketId === "over_2_5" && !String(row.predicted_pick || "").toLowerCase().includes("over")) return null;
  if (marketId === "under_2_5" && !String(row.predicted_pick || "").toLowerCase().includes("under")) return null;
  return row;
}

export function needsClientFiltering({ search, marketFilter }) {
  const hasSearch = Boolean(String(search || "").trim());
  const hasMarket = marketFilter && marketFilter !== "all" && marketFilter !== "best_bets";
  return hasSearch || hasMarket;
}
