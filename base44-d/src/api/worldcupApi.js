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
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
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
 */
export async function runPrediction(fixtureId, params = {}) {
  const token = getAuthToken();
  const headers = { Accept: "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(buildApiUrl(`/api/predict/${fixtureId}`, params), {
    method: "POST",
    headers,
  });
  return parseJsonResponse(response);
}

export { buildApiUrl as buildUrl };
