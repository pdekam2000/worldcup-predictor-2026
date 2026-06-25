/**
 * WorldCup Predictor FastAPI client — matches, predictions, health.
 */

import { getAuthToken } from "@/api/authApi";
import { buildApiUrl } from "@/lib/config";

async function parseJsonResponse(response) {
  let payload;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const message =
      payload?.detail?.message ||
      payload?.detail ||
      payload?.message ||
      `API request failed (${response.status})`;
    const err = new Error(typeof message === "string" ? message : JSON.stringify(message));
    if (payload?.detail?.code) {
      err.code = payload.detail.code;
    }
    if (payload?.detail?.upgrade_url) {
      err.upgradeUrl = payload.detail.upgrade_url;
    }
    const waitMatch = typeof message === "string" ? message.match(/wait (\d+)s/i) : null;
    if (waitMatch) {
      err.cooldownSeconds = parseInt(waitMatch[1], 10);
    }
    throw err;
  }
  return payload;
}

/** Map backend match row to MatchCenter card shape. */
export function mapUpcomingMatch(row) {
  return {
    id: String(row.fixture_id),
    fixture_id: row.fixture_id,
    match_date: row.date,
    league: row.league,
    competition_key: row.competition_key ?? null,
    competition_name: row.competition_name ?? row.league,
    competition_emoji: row.competition_emoji ?? null,
    competition_country: row.competition_country ?? row.country ?? null,
    home_team: row.home_team,
    away_team: row.away_team,
    status: row.status,
    bucket: row.bucket,
    season: row.season,
    home_team_logo: row.home_team_logo ?? null,
    away_team_logo: row.away_team_logo ?? null,
    country: row.country ?? null,
    venue: row.venue ?? null,
    city: row.city ?? null,
    has_prediction: Boolean(row.has_prediction),
    prediction_summary: row.prediction_summary ?? null,
  };
}

/**
 * @param {{
 *   status?: 'upcoming'|'live'|'finished'|'all'|'predicted',
 *   page?: number,
 *   page_size?: number,
 *   team?: string,
 *   competition?: string,
 *   season?: number,
 *   has_prediction?: boolean,
 *   include_summary?: boolean,
 *   country?: string,
 *   elite_only?: boolean,
 * }} params
 */
export async function fetchMatches(params = {}) {
  const response = await fetch(buildApiUrl("/api/matches", params));
  const payload = await parseJsonResponse(response);
  const rows = Array.isArray(payload?.matches) ? payload.matches : [];
  return {
    status: payload?.status ?? "ok",
    competition: payload?.competition ?? null,
    total_count: payload?.total_count ?? rows.length,
    page: payload?.page ?? 1,
    page_size: payload?.page_size ?? rows.length,
    total_pages: payload?.total_pages ?? 1,
    count: payload?.count ?? rows.length,
    predicted_fixture_count: payload?.predicted_fixture_count ?? 0,
    source_label: payload?.source_label ?? null,
    competitions_included: payload?.competitions_included ?? null,
    matches: rows.map(mapUpcomingMatch),
  };
}

export async function fetchCompetitions({ includeCounts = true } = {}) {
  const response = await fetch(
    buildApiUrl("/api/competitions", includeCounts ? { include_counts: true } : {})
  );
  const payload = await parseJsonResponse(response);
  return {
    status: payload?.status ?? "ok",
    count: payload?.count ?? 0,
    total_upcoming: payload?.total_upcoming ?? 0,
    competitions: payload?.competitions ?? [],
  };
}

export async function fetchHealth() {
  const response = await fetch(buildApiUrl("/api/health"));
  return parseJsonResponse(response);
}

/**
 * @param {{ competition?: string, season?: number, limit?: number }} params
 */
export async function fetchUpcomingMatches(params = {}) {
  const response = await fetch(buildApiUrl("/api/matches/upcoming", params));
  const payload = await parseJsonResponse(response);
  const rows = Array.isArray(payload?.matches) ? payload.matches : [];
  return {
    status: payload?.status ?? "ok",
    count: payload?.count ?? rows.length,
    matches: rows.map(mapUpcomingMatch),
  };
}

/**
 * @param {number|string} fixtureId
 * @param {{ competition?: string, season?: number, locale?: string }} params
 * @returns {Promise<{ status: string, cached: boolean, data?: object }>}
 */
export async function fetchCachedPrediction(fixtureId, params = {}) {
  const token = getAuthToken();
  const headers = { Accept: "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(buildApiUrl(`/api/predict/${fixtureId}`, params), {
    method: "GET",
    headers,
  });
  if (response.status === 404) {
    return { status: "not_cached", cached: false };
  }
  const payload = await parseJsonResponse(response);
  return { status: payload?.status ?? "ok", cached: true, data: payload };
}

/**
 * @param {number|string} fixtureId
 * @param {{ competition?: string, season?: number, locale?: string, forceRefresh?: boolean }} params
 */
export async function runPrediction(fixtureId, params = {}) {
  const { forceRefresh = false, ...queryParams } = params;
  const token = getAuthToken();
  const headers = { Accept: "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const qs = { ...queryParams };
  if (forceRefresh) {
    qs.force_refresh = "true";
  }
  const response = await fetch(buildApiUrl(`/api/predict/${fixtureId}`, qs), {
    method: "POST",
    headers,
  });
  return parseJsonResponse(response);
}

/** Normalize prediction API payload for UI — Phase 30A/30C. */
export function normalizePredictionPayload(data) {
  if (!data || typeof data !== "object") return data;
  const ou =
    data.probabilities?.over_under_2_5 ??
    data.detailed_markets?.over_under_25 ??
    null;
  return {
    ...data,
    recommended_bets: Array.isArray(data.recommended_bets) ? data.recommended_bets : [],
    detailed_markets: data.detailed_markets ?? {},
    market_ranking: Array.isArray(data.market_ranking) ? data.market_ranking : [],
    safe_pick: data.safe_pick ?? null,
    value_pick: data.value_pick ?? null,
    aggressive_pick: data.aggressive_pick ?? null,
    caution_pick: data.caution_pick ?? null,
    best_available_pick: data.best_available_pick ?? null,
    user_visible_pick: data.user_visible_pick ?? null,
    pick_tier: data.pick_tier ?? (data.no_bet ? "caution" : "official"),
    caution_reason: data.caution_reason ?? null,
    confidence_gap_to_threshold: data.confidence_gap_to_threshold ?? null,
    accuracy_tracking: data.accuracy_tracking ?? null,
    probabilities: {
      ...(data.probabilities ?? {}),
      over_under_2_5: ou,
    },
  };
}
