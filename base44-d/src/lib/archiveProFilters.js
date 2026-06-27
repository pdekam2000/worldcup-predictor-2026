/** Phase A12 — extended archive filters (client-side on API rows). */

import {
  STATUS_FILTERS,
  SCOPE_TABS,
  MARKET_FILTERS,
  SORT_OPTIONS,
  DATE_QUICK_FILTERS,
  filterArchiveItems,
  needsClientFiltering,
} from "@/lib/archiveFilters";

export { STATUS_FILTERS, SCOPE_TABS, MARKET_FILTERS, SORT_OPTIONS, DATE_QUICK_FILTERS, needsClientFiltering };

export const LEAGUE_FILTERS = [
  { id: "all", label: "All leagues" },
  { id: "world_cup_2026", label: "World Cup 2026" },
  { id: "premier_league", label: "Premier League" },
  { id: "champions_league", label: "Champions League" },
  { id: "la_liga", label: "La Liga" },
  { id: "serie_a", label: "Serie A" },
  { id: "bundesliga", label: "Bundesliga" },
];

export const CONFIDENCE_TIERS = [
  { id: "all", label: "All confidence" },
  { id: "elite", label: "Elite (75%+)" },
  { id: "high", label: "High (65%+)" },
  { id: "medium", label: "Medium (50%+)" },
  { id: "low", label: "Low (<50%)" },
];

export function confidenceTier(confidence) {
  const c = Number(confidence);
  if (Number.isNaN(c)) return "unknown";
  const pct = c <= 1 ? c * 100 : c;
  if (pct >= 75) return "elite";
  if (pct >= 65) return "high";
  if (pct >= 50) return "medium";
  return "low";
}

export function matchesLeague(item, leagueId) {
  if (!leagueId || leagueId === "all") return true;
  const league = String(item?.league || item?.competition_key || "").toLowerCase();
  const key = leagueId.replace(/_/g, " ");
  return league.includes(key) || league.includes(leagueId.replace(/_/g, ""));
}

export function matchesConfidenceTier(item, tierId) {
  if (!tierId || tierId === "all") return true;
  const conf = item?.predicted_confidence ?? item?.confidence;
  return confidenceTier(conf) === tierId;
}

export function matchesDateRange(item, from, to) {
  const raw = item?.match_date || item?.generated_at || item?.prediction_date;
  if (!raw) return true;
  const t = new Date(raw).getTime();
  if (from) {
    const f = new Date(from).getTime();
    if (t < f) return false;
  }
  if (to) {
    const end = new Date(to);
    end.setHours(23, 59, 59, 999);
    if (t > end.getTime()) return false;
  }
  return true;
}

export function matchesEngineVersion(item, version) {
  if (!version || version === "all") return true;
  const v = String(item?.engine_version || item?.pipeline_version || "").toLowerCase();
  return v.includes(String(version).toLowerCase());
}

export function filterArchivePro(items, filters) {
  let rows = filterArchiveItems(items, {
    search: filters.search,
    marketFilter: filters.marketFilter,
  });
  rows = rows.filter(
    (item) =>
      matchesLeague(item, filters.league) &&
      matchesConfidenceTier(item, filters.confidenceTier) &&
      matchesDateRange(item, filters.dateFrom, filters.dateTo) &&
      matchesEngineVersion(item, filters.engineVersion)
  );
  return rows;
}

export function needsExtendedClientFiltering(filters) {
  return (
    needsClientFiltering(filters) ||
    (filters.league && filters.league !== "all") ||
    (filters.confidenceTier && filters.confidenceTier !== "all") ||
    filters.dateFrom ||
    filters.dateTo ||
    (filters.engineVersion && filters.engineVersion !== "all") ||
    (filters.dateQuick && filters.dateQuick !== "all")
  );
}

function formatDateInput(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function dateRangeFromQuickFilter(quickId) {
  const id = String(quickId || "all").toLowerCase();
  if (id === "all" || !id) {
    return { dateFrom: "", dateTo: "" };
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  if (id === "yesterday") {
    const y = new Date(today);
    y.setDate(y.getDate() - 1);
    const s = formatDateInput(y);
    return { dateFrom: s, dateTo: s };
  }
  if (id === "7d") {
    const start = new Date(today);
    start.setDate(start.getDate() - 7);
    return { dateFrom: formatDateInput(start), dateTo: formatDateInput(today) };
  }
  if (id === "30d") {
    const start = new Date(today);
    start.setDate(start.getDate() - 30);
    return { dateFrom: formatDateInput(start), dateTo: formatDateInput(today) };
  }
  return { dateFrom: "", dateTo: "" };
}
