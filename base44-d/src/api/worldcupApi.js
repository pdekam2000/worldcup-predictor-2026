/**
 * WorldCup Predictor FastAPI client — UI layer only (not Base44 cloud).
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

function buildUrl(path, params = {}) {
  const url = new URL(path, API_BASE);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });
  return url.toString();
}

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
  const response = await fetch(buildUrl("/api/health"));
  return parseJsonResponse(response);
}

/**
 * @param {{ competition?: string, season?: number, limit?: number }} params
 */
export async function fetchUpcomingMatches(params = {}) {
  const response = await fetch(buildUrl("/api/matches/upcoming", params));
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
  const response = await fetch(
    buildUrl(`/api/predict/${fixtureId}`, params),
    { method: "POST", headers: { Accept: "application/json" } },
  );
  return parseJsonResponse(response);
}

export { API_BASE };
