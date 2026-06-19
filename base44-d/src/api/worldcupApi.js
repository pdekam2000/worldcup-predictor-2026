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
    match_date: row.date,
    league: row.league,
    home_team: row.home_team,
    away_team: row.away_team,
    status: row.status,
    season: row.season,
    home_team_logo: row.home_team_logo ?? null,
    away_team_logo: row.away_team_logo ?? null,
    country: row.country ?? null,
    venue: row.venue ?? null,
    city: row.city ?? null,
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

export { buildApiUrl as buildUrl };
