/** Phase A11 + A16 — extract display data from cached prediction payloads (read-only). */

import { tierFromScore, qualityColorClass } from "@/lib/betQualityOverlay";

const COMP_EMOJI = {
  world_cup_2026: "🏆",
  champions_league: "🇪🇺",
  premier_league: "🏴",
  la_liga: "🇪🇸",
  serie_a: "🇮🇹",
  bundesliga: "🇩🇪",
  ligue_1: "🇫🇷",
};

export function roundPct(v) {
  if (v == null || Number.isNaN(Number(v))) return null;
  const n = Number(v);
  return n <= 1 ? Math.round(n * 100) : Math.round(n);
}

/** Coerce pick/selection values to a safe display string (never return raw objects). */
export function safeMarketSelection(v) {
  if (v == null) return null;
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
    const s = String(v).trim();
    return s || null;
  }
  if (typeof v === "object") {
    const inner = v.pick ?? v.selection ?? v.label ?? v.market ?? v.team ?? v.player;
    if (inner != null && inner !== v) return safeMarketSelection(inner);
    return null;
  }
  return null;
}

/** Any React-safe display scalar — never pass objects to JSX children. */
export function safeDisplayText(v, fallback = null) {
  const inner = safeMarketSelection(v);
  if (inner != null) return inner;
  if (v == null) return fallback;
  if (typeof v === "number" && !Number.isNaN(v)) return String(v);
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "object") {
    if (Array.isArray(v)) return v.map((x) => safeDisplayText(x, "")).filter(Boolean).join(", ") || fallback;
    const prob = v.home ?? v.away ?? v.draw;
    if (prob != null && typeof prob === "number") {
      const top = Object.entries(v).sort((a, b) => Number(b[1]) - Number(a[1]))[0];
      if (top) return `${top[0]} (${(Number(top[1]) <= 1 ? Number(top[1]) * 100 : Number(top[1])).toFixed(1)}%)`;
    }
    return fallback;
  }
  const s = String(v).trim();
  return s && s !== "[object Object]" ? s : fallback;
}

export function fmtMarketSel(v) {
  const raw = safeMarketSelection(v);
  if (!raw) return null;
  const map = {
    home: "Home Win",
    away: "Away Win",
    draw: "Draw",
    home_win: "Home Win",
    away_win: "Away Win",
    over_2_5: "Over 2.5",
    under_2_5: "Under 2.5",
    yes: "Yes",
    no: "No",
  };
  return map[String(raw).toLowerCase()] || String(raw).replace(/_/g, " ");
}

export function competitionEmoji(key) {
  return COMP_EMOJI[key] || "⚽";
}

export function buildSummary(prediction, { isOwner = false } = {}) {
  if (!prediction) return null;
  const noBet = Boolean(prediction.no_bet);
  const overlay = prediction.publication_overlay || {};
  const pick =
    prediction.best_available_pick ||
    prediction.value_pick ||
    prediction.safe_pick ||
    prediction.user_visible_pick;
  let pickLabel = safeDisplayText(
    typeof pick === "object" ? pick.pick || pick.selection || pick.market || pick : pick || prediction.prediction,
    null
  );
  if (!pickLabel) {
    const mw = prediction.detailed_markets?.match_winner;
    if (mw?.selection) pickLabel = mw.selection;
  }
  const market = typeof pick === "object" ? pick.market : "1x2";
  const conf = roundPct(prediction.confidence);
  const prob = roundPct(
    typeof pick === "object" ? pick.probability || pick.confidence : prediction.confidence
  );
  const tier = prediction.pick_tier || (noBet ? "caution" : "official");
  const valueRating =
    prediction.value_rating ||
    prediction.betting_intelligence?.value_grade ||
    (tier === "elite" ? "A" : tier === "official" ? "B" : "C");
  const odds =
    prediction.expected_odds ||
    prediction.betting_intelligence?.fair_odds ||
    (typeof pick === "object" ? pick.odds_decimal : null);
  const agreement = roundPct(prediction.specialist_summary?.aggregated_score);

  const publicStatus = overlay.public_recommendation_status;
  const caution = publicStatus === "caution_best_available" || overlay.caution_label;
  let bestPick = null;
  if (publicStatus === "published" || caution) {
    const sel = pickLabel || safeDisplayText(overlay.public_best_pick, null);
    if (sel) {
      bestPick =
        typeof sel === "string" && sel.includes(":")
          ? sel
          : `${market !== "1x2" ? `${market}: ` : ""}${fmtMarketSel(sel) || sel}`;
    }
  }
  if (!bestPick && overlay.public_best_pick) {
    bestPick = safeDisplayText(overlay.public_best_pick, null);
  }

  const bqs = overlay.bet_quality_score ?? prediction.bet_quality_score;
  const bqt = overlay.bet_quality_tier ?? prediction.bet_quality_tier;
  const bqc = overlay.bet_quality_color ?? prediction.bet_quality_color;

  return {
    bestPick,
    confidence: conf,
    probability: prob,
    valueRating: safeDisplayText(valueRating, "—"),
    risk: prediction.risk_level || "medium",
    expectedOdds: safeDisplayText(odds, null),
    modelAgreement: agreement,
    noBet: isOwner ? noBet : undefined,
    wdeReasons: isOwner ? overlay.wde_no_bet_reasons : undefined,
    tier,
    caution,
    cautionLabel: safeDisplayText(overlay.caution_label, caution ? "Caution — Best Available" : null),
    betQualityScore: bqs,
    betQualityTier: bqt,
    betQualityColor: bqc,
    qualityReason: overlay.quality_reason,
    publicStatus,
    unavailableReason: publicStatus === "unavailable" ? overlay.quality_reason : null,
  };
}

export function extractMatchInsights(prediction) {
  if (!prediction) return [];
  const insights = [];
  const agents = prediction?.specialist_summary?.agents || {};
  if (agents.form) insights.push("Strong home form");
  if (agents.lineup || agents.expected_lineup_agent) insights.push("Lineup advantage");
  if (agents.odds) insights.push("Odds movement");
  if (prediction?.sportmonks_xg && Object.keys(prediction.sportmonks_xg).length) insights.push("xG advantage");
  if (prediction?.pressure_intelligence || prediction?.sportmonks_pressure) insights.push("Pressure advantage");
  if (prediction?.head_to_head || prediction?.h2h) insights.push("Historical H2H");
  return insights;
}

export function buildAiInsights(prediction) {
  const base = extractMatchInsights(prediction);
  const agents = prediction?.specialist_summary?.agents || {};
  const extra = [];
  if (agents.injury || agents.injury_agent) extra.push("Away injuries considered");
  if (agents.form) extra.push("Recent form analyzed");
  if (agents.referee) extra.push("Referee trend");
  if (prediction?.weather_intelligence?.available) extra.push("Weather impact");
  if (agents.lineup || agents.expected_lineup_agent) extra.push("Lineup quality");
  if (prediction?.head_to_head || prediction?.h2h) extra.push("Head-to-head trend");
  const combined = [...new Set([...base, ...extra])];
  return combined.slice(0, 10);
}

export function groupMarkets(prediction, { isOwner = false } = {}) {
  const dm = prediction?.detailed_markets || {};
  const probs = prediction?.probabilities || {};
  const risk = prediction?.risk_level || "medium";
  const mq = prediction?.publication_overlay?.market_quality || {};
  const evalStatuses = prediction?.match_evaluation?.market_statuses || {};

  const row = (title, selection, probability, confidence, reason, market, raw, qualityBlock) => {
    const q = qualityBlock || (market && mq[market]) || {};
    const score = q.bet_quality_score;
    const tierMeta = score != null ? tierFromScore(score) : null;
    const safeSel = fmtMarketSel(selection) || safeMarketSelection(selection);
    return {
      title,
      selection: safeSel,
      probability: roundPct(probability),
      confidence: roundPct(confidence ?? probability),
      reason: reason || q.quality_reason,
      risk,
      market,
      raw: raw ?? selection,
      betQualityScore: score ?? tierMeta?.bet_quality_score,
      betQualityTier: q.bet_quality_tier ?? tierMeta?.bet_quality_tier,
      betQualityColor: q.bet_quality_color ?? tierMeta?.bet_quality_color,
      internalStatus: isOwner ? q.internal_status : undefined,
      unavailable: q.internal_status === "unavailable",
      unavailableReason: q.quality_reason,
      evaluationStatus: market ? evalStatuses[market] : undefined,
    };
  };

  const winner = [
    row("1X2", prediction.prediction || dm.match_winner?.selection, prediction.confidence, prediction.confidence, null, "1x2", prediction.prediction, mq["1x2"]),
    row("Double Chance", dm.double_chance?.selection, dm.double_chance?.probability, dm.double_chance?.confidence, null, "double_chance", dm.double_chance?.selection, mq.double_chance),
  ].filter((r) => r.selection || r.unavailable);

  const goals = [
    row("Over/Under 2.5", probs.over_under_2_5?.selection || dm.over_under_25?.selection, probs.over_under_2_5?.probability || dm.over_under_25?.probability, probs.over_under_2_5?.confidence, null, "over_under_2_5", probs.over_under_2_5?.selection, mq.over_under_2_5),
    row("BTTS", probs.btts?.selection || dm.btts?.selection, probs.btts?.probability || dm.btts?.probability, probs.btts?.confidence, null, "btts", probs.btts?.selection, mq.btts),
  ].filter((r) => r.selection || r.unavailable);

  const timing = [
    row("First Goal Team", dm.first_goal?.team ? `${dm.first_goal.team} first` : null, dm.first_goal?.probability, dm.first_goal?.confidence, dm.first_goal?.minute_range ? `Window: ${dm.first_goal.minute_range}` : null, "first_goal_team", dm.first_goal?.team),
  ].filter((r) => r.selection);

  const scorers = [
    row("Goalscorer", dm.goalscorer?.player, dm.goalscorer?.probability, dm.goalscorer?.confidence, dm.goalscorer?.team ? `Team: ${dm.goalscorer.team}` : null, "goalscorer", dm.goalscorer?.player),
  ].filter((r) => r.selection);

  const halftime = [
    row("Half Time", dm.halftime?.selection, dm.halftime?.probability, dm.halftime?.confidence, null, "halftime", dm.halftime?.selection),
  ].filter((r) => r.selection);

  const correctScore = (Array.isArray(dm.correct_scores) ? dm.correct_scores : []).slice(0, 5).map((s) =>
    row("Correct Score", s.label || s.scoreline, s.probability, s.confidence, null, "correct_score", s.label)
  );

  const special = (Array.isArray(prediction.recommended_bets) ? prediction.recommended_bets : [])
    .slice(0, 6)
    .map((b) =>
      row(
        safeDisplayText(b.market, "Special"),
        b.pick,
        b.probability,
        b.confidence,
        b.reasoning,
        safeDisplayText(b.market, "special"),
        b.pick
      )
    );

  return [
    { id: "winner", label: "Winner", markets: winner },
    { id: "goals", label: "Goals", markets: goals },
    { id: "timing", label: "Goal Timing", markets: timing },
    { id: "scorers", label: "Goalscorers", markets: scorers },
    { id: "halftime", label: "Half Time", markets: halftime },
    { id: "correct_score", label: "Correct Score", markets: correctScore },
    { id: "special", label: "Special Markets", markets: special },
  ].filter((g) => g.markets.length > 0);
}

export function buildTeamComparison(prediction) {
  const xg = prediction?.sportmonks_xg || {};
  const intel = prediction?.team_intelligence || prediction?.match_intelligence || {};
  const home = intel.home || xg.home || {};
  const away = intel.away || xg.away || {};
  const metric = (label, h, a) => ({ label, home: h ?? null, away: a ?? null });

  return [
    metric("Attack", home.attack ?? home.xg_for, away.attack ?? away.xg_for),
    metric("Defense", home.defense ?? home.xg_against, away.defense ?? away.xg_against),
    metric("Form", home.form_score ?? home.form, away.form_score ?? away.form),
    metric("xG", home.xg ?? home.expected_goals, away.xg ?? away.expected_goals),
    metric("Shots", home.shots, away.shots),
    metric("Possession", home.possession, away.possession),
    metric("Pressure", home.pressure, away.pressure),
  ].filter((m) => m.home != null || m.away != null);
}

export function buildOddsCenter(prediction) {
  const bi = prediction?.betting_intelligence || {};
  const odds = prediction?.odds_intelligence || prediction?.market_odds || {};
  const implied = odds.implied_probabilities || bi.implied_probabilities || {};
  const movement = odds.movement || bi.odds_movement || prediction?.odds_movement;
  return {
    current: odds.current || bi.current_odds || odds,
    implied,
    movement,
    valueIndicator: bi.value_grade || bi.value_rating || prediction?.value_rating,
    consensus: odds.bookmaker_count || bi.bookmaker_count || odds.consensus,
    homeWin: implied.home ?? implied.home_win,
    draw: implied.draw,
    awayWin: implied.away ?? implied.away_win,
  };
}

export function buildXgSection(prediction) {
  const xg = prediction?.sportmonks_xg || {};
  if (!xg || (typeof xg === "object" && !Object.keys(xg).length)) return null;
  const home = xg.home_xg ?? xg.home?.xg ?? xg.expected_home;
  const away = xg.away_xg ?? xg.away?.xg ?? xg.expected_away;
  const diff = home != null && away != null ? Number((Number(home) - Number(away)).toFixed(2)) : null;
  return {
    home,
    away,
    difference: diff,
    trend: xg.trend || xg.form_trend,
    raw: xg,
  };
}

export function buildPressureSection(prediction) {
  const p = prediction?.pressure_intelligence || prediction?.sportmonks_pressure || {};
  if (!p || !Object.keys(p).length) return null;
  return {
    timeline: Array.isArray(p.timeline) ? p.timeline : p.periods || [],
    advantage: p.advantage || p.pressure_advantage,
    momentum: p.momentum_summary || p.momentum,
    home: p.home_pressure ?? p.home,
    away: p.away_pressure ?? p.away,
  };
}

export function buildLineupsSection(prediction) {
  const dm = prediction?.detailed_markets || {};
  const lineup = dm.lineup || prediction?.expected_lineup || prediction?.lineup_intelligence || {};
  const homeXi = lineup.home?.starting_xi || lineup.home_lineup || lineup.home?.players || [];
  const awayXi = lineup.away?.starting_xi || lineup.away_lineup || lineup.away?.players || [];
  return {
    homeFormation: lineup.home?.formation,
    awayFormation: lineup.away?.formation,
    homeXi: Array.isArray(homeXi) ? homeXi : [],
    awayXi: Array.isArray(awayXi) ? awayXi : [],
    unavailable: lineup.unavailable || prediction?.injuries || [],
    injuries: lineup.injuries || [],
    suspensions: lineup.suspensions || [],
  };
}

export function buildConfidenceExplanation(prediction) {
  const conf = roundPct(prediction?.confidence) || 0;
  const breakdown = prediction?.confidence_breakdown || {};
  const factors = [];
  const push = (label, score) => {
    const pct = roundPct(score);
    if (pct != null && pct > 0) factors.push({ label, score: pct });
  };
  push("Form data", breakdown.form_score ?? breakdown.form);
  push("Head-to-head", breakdown.h2h_score ?? breakdown.h2h);
  push("Injuries", breakdown.injuries_score ?? breakdown.injuries);
  push("Lineups", breakdown.lineups_score ?? breakdown.lineups);
  push("Odds alignment", breakdown.odds_score ?? breakdown.odds);
  push("Data quality", breakdown.data_quality_score ?? breakdown.data_quality);
  if (!factors.length && prediction?.data_quality != null) {
    push("Data quality", prediction.data_quality);
  }
  if (!factors.length && prediction?.specialist_summary?.aggregated_score != null) {
    push("Specialist agreement", prediction.specialist_summary.aggregated_score);
  }
  const totalFactor = factors.reduce((s, f) => s + f.score, 0) || 1;
  return {
    confidence: conf,
    factors: factors.map((f) => ({ ...f, weight: Math.round((f.score / totalFactor) * 100) })),
    gap: prediction?.confidence_gap_to_threshold,
    cautionReason: prediction?.caution_reason,
  };
}

export function buildAgentContribution(prediction) {
  const agents = prediction?.specialist_summary?.agents || {};
  const map = [
    { key: "wde", labels: ["wde", "decision"], title: "WDE" },
    { key: "egie", labels: ["egie", "ensemble"], title: "EGIE" },
    { key: "odds", labels: ["odds", "odds_market_agent"], title: "Odds" },
    { key: "weather", labels: ["weather", "weather_agent"], title: "Weather" },
    { key: "lineups", labels: ["lineup", "lineup_agent", "expected_lineup_agent"], title: "Lineups" },
    { key: "market", labels: ["sportmonks_prediction_agent", "tournament_context_agent"], title: "Market Intelligence" },
    { key: "calibration", labels: ["calibration", "xg_intelligence_agent"], title: "Calibration" },
  ];
  return map.map(({ key, labels, title }) => {
    const agent = labels.map((l) => agents[l]).find(Boolean) || agents[key];
    return {
      key,
      title,
      status: agent?.status || "—",
      impact: roundPct(agent?.impact_score),
      domain: agent?.domain,
    };
  });
}

export function aiScoreFromPrediction(prediction) {
  let score = 42;
  const conf = Number(prediction?.confidence || 0);
  score += Math.min(28, conf * 0.32);
  if (prediction?.pick_tier === "elite") score += 12;
  if (prediction?.no_bet) score -= 18;
  if (prediction?.sportmonks_xg) score += 4;
  if (prediction?.weather_intelligence?.available) score += 2;
  score = Math.max(0, Math.min(100, Math.round(score)));
  const label = score >= 95 ? "Elite" : score >= 87 ? "Strong" : score >= 73 ? "Good" : score >= 58 ? "Watch" : "Skip";
  return { score, label };
}

export function fixtureStatusFromPrediction(prediction) {
  if (prediction?.accuracy_tracking?.evaluated) return "Evaluated";
  if (prediction?.cached_at || prediction?.confidence != null) return "Prediction Ready";
  return "Waiting for Lineups";
}
