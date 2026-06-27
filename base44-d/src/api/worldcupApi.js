/**
 * WorldCup Predictor FastAPI client — matches, predictions, health.
 */

import { getAuthToken } from "@/api/authApi";
import { fetchPredOpsSnapshotLatest } from "@/api/saasApi";
import { buildApiUrl } from "@/lib/config";
import { apiFootballTeamLogoUrl } from "@/lib/imageResolver";

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
    match_date: row.date ?? row.match_date,
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
    resolved_season: row.resolved_season ?? row.season,
    home_team_logo: row.home_team_logo ?? apiFootballTeamLogoUrl(row.home_team_id) ?? null,
    away_team_logo: row.away_team_logo ?? apiFootballTeamLogoUrl(row.away_team_id) ?? null,
    home_team_id: row.home_team_id ?? null,
    away_team_id: row.away_team_id ?? null,
    country: row.country ?? null,
    venue: row.venue ?? null,
    city: row.city ?? null,
    has_prediction: Boolean(row.has_prediction),
    prediction_summary: row.prediction_summary ?? null,
    ai_match_score: row.ai_match_score ?? null,
    match_insights: row.match_insights ?? [],
    fixture_status_label: row.fixture_status_label ?? null,
    owner_meta: row.owner_meta ?? null,
    match_evaluation: row.match_evaluation ?? null,
    result_status: row.result_status ?? row.match_evaluation?.result_status ?? null,
    final_score: row.final_score ?? row.match_evaluation?.final_score ?? null,
  };
}

async function authFetch(url) {
  const token = getAuthToken();
  const headers = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(url, { headers });
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
  const response = await authFetch(buildApiUrl("/api/matches", params));
  const payload = await parseJsonResponse(response);
  const rows = Array.isArray(payload?.matches) ? payload.matches : [];
  const elite = Array.isArray(payload?.elite_picks_today) ? payload.elite_picks_today : [];
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
    load_ms: payload?.load_ms ?? null,
    cache_hits: payload?.cache_hits ?? null,
    elite_picks_today: elite.map(mapUpcomingMatch),
    matches: rows.map(mapUpcomingMatch),
  };
}

export async function fetchElitePicksToday(params = {}) {
  const response = await fetch(buildApiUrl("/api/matches/elite-picks-today", params));
  const payload = await parseJsonResponse(response);
  const picks = Array.isArray(payload?.picks) ? payload.picks : [];
  return { status: payload?.status ?? "ok", count: payload?.count ?? picks.length, picks: picks.map(mapUpcomingMatch) };
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

export async function fetchMatchEvaluation(fixtureId) {
  const response = await fetch(buildApiUrl(`/api/matches/${fixtureId}/evaluation`));
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
  const tryFetch = async (queryParams) => {
    const response = await fetch(buildApiUrl(`/api/predict/${fixtureId}`, queryParams), {
      method: "GET",
      headers,
    });
    if (response.status === 404 || response.status === 400) {
      return null;
    }
    const payload = await parseJsonResponse(response);
    return { status: payload?.status ?? "ok", cached: true, data: payload, source: payload?.cache_source || "predict_cache" };
  };

  let result = await tryFetch(params);
  if (!result && params.competition) {
    const { competition, ...rest } = params;
    result = await tryFetch(rest);
  }
  if (!result) {
    return { status: "not_cached", cached: false };
  }
  return result;
}

/** Map public PredOps snapshot (sanitized) into prediction UI shape when predict cache misses. */
export function predopsSnapshotToPrediction(apiResponse) {
  const snapshot = apiResponse?.snapshot ?? apiResponse;
  if (!snapshot || typeof snapshot !== "object") return null;
  const overlay = snapshot.publication_overlay || {};
  const markets = snapshot.markets || {};
  const detailed_markets = {};
  const probabilities = {};

  const assignMarket = (key, title, block) => {
    if (!block || typeof block !== "object") return;
    const sel = block.final_selected_prediction;
    const pick = typeof sel === "object" ? sel.pick ?? sel.selection ?? sel.label : sel;
    const prob = typeof sel === "object" ? sel.probability ?? sel.confidence : null;
    const conf = typeof sel === "object" ? sel.confidence ?? sel.probability : prob;
    if (key === "1x2" || key === "match_winner") {
      detailed_markets.match_winner = { selection: pick, probability: prob, confidence: conf };
    } else if (key === "double_chance") {
      detailed_markets.double_chance = { selection: pick, probability: prob, confidence: conf };
    } else if (key === "btts") {
      detailed_markets.btts = { selection: pick, probability: prob, confidence: conf };
      probabilities.btts = { selection: pick, probability: prob, confidence: conf };
    } else if (key === "over_under_2_5" || key === "over_under_25") {
      detailed_markets.over_under_25 = { selection: pick, probability: prob, confidence: conf };
      probabilities.over_under_2_5 = { selection: pick, probability: prob, confidence: conf };
    } else {
      detailed_markets[key] = { selection: pick, probability: prob, confidence: conf };
    }
  };

  Object.entries(markets).forEach(([mid, block]) => assignMarket(mid, mid, block));

  const mw = detailed_markets.match_winner;
  return normalizePredictionPayload({
    fixture_id: snapshot.fixture_id,
    competition_key: snapshot.competition_key,
    publication_overlay: overlay,
    detailed_markets,
    probabilities,
    prediction: mw?.selection || overlay.public_best_pick,
    confidence: overlay.confidence ?? mw?.confidence ?? mw?.probability,
    bet_quality_score: overlay.bet_quality_score,
    bet_quality_tier: overlay.bet_quality_tier,
    no_bet: snapshot.coverage_state === "no_bet",
    cache_source: "predops_public_snapshot",
    snapshot_id: snapshot.snapshot_id,
    source_model: snapshot.coverage_state === "no_bet" ? "EGIE / WDE" : "Model A",
  });
}

/**
 * Load prediction: predict cache → PredOps snapshot → optional POST run.
 * @param {number|string} fixtureId
 * @param {{ competition?: string, season?: number, locale?: string, allowRun?: boolean }} params
 */
export async function fetchPredictionForFixture(fixtureId, params = {}) {
  const { allowRun = false, ...queryParams } = params;
  const cached = await fetchCachedPrediction(fixtureId, queryParams);
  if (cached.cached && cached.data) {
    return { status: "ok", cached: true, data: cached.data, source: cached.source || "predict_cache" };
  }
  try {
    const snapRes = await fetchPredOpsSnapshotLatest(fixtureId);
    const mapped = predopsSnapshotToPrediction(snapRes);
    if (mapped) {
      return { status: "ok", cached: true, data: mapped, source: "predops_public_snapshot" };
    }
  } catch (err) {
    console.warn("[fetchPredictionForFixture] PredOps fallback failed", err);
  }
  if (allowRun) {
    const payload = await runPrediction(fixtureId, queryParams);
    return { status: "ok", cached: false, data: payload, source: "live_run" };
  }
  return { status: "not_found", cached: false, data: null };
}

/** Find match row from list API for header logos / team names. */
export async function fetchMatchMeta(fixtureId, { competition = "all" } = {}) {
  const tryFind = (rows) =>
    (rows || []).find((m) => String(m.fixture_id ?? m.id) === String(fixtureId)) || null;
  const primary = await fetchMatches({
    competition,
    page_size: 120,
    include_summary: true,
    status: "all",
  });
  let match = tryFind(primary.matches);
  if (!match && competition !== "all") {
    const all = await fetchMatches({ competition: "all", page_size: 200, include_summary: true, status: "all" });
    match = tryFind(all.matches);
  }
  return match;
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

/** Normalize prediction API payload for UI — Phase 30A/30C + H4 safe scalars. */
export function normalizePredictionPayload(data) {
  if (!data || typeof data !== "object") return data;
  const ou =
    data.probabilities?.over_under_2_5 ??
    data.detailed_markets?.over_under_25 ??
    null;
  const overlay = data.publication_overlay && typeof data.publication_overlay === "object"
    ? { ...data.publication_overlay }
    : {};
  if (overlay.public_best_pick != null && typeof overlay.public_best_pick === "object") {
    overlay.public_best_pick =
      overlay.public_best_pick.pick ||
      overlay.public_best_pick.selection ||
      overlay.public_best_pick.label ||
      null;
  }
  return {
    ...data,
    publication_overlay: overlay,
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
