/** Combo slip builder — uses cached prediction summaries only. */

const CONFLICT_GROUPS = [
  ["home_win", "home", "away_win", "away", "draw"],
  ["over_2_5", "under_2_5", "over_1_5", "under_1_5"],
  ["yes", "no"],
];

function normSel(v) {
  return String(v || "").toLowerCase().replace(/\s+/g, "_");
}

function hasConflict(existing, candidate) {
  const cSel = normSel(candidate.selection);
  for (const leg of existing) {
    const lSel = normSel(leg.selection);
    for (const group of CONFLICT_GROUPS) {
      if (group.includes(cSel) && group.includes(lSel) && cSel !== lSel) {
        return true;
      }
    }
    if (
      leg.fixture_id === candidate.fixture_id &&
      normSel(leg.market) === normSel(candidate.market) &&
      lSel !== cSel
    ) {
      return true;
    }
  }
  return false;
}

function starsFromSummary(summary) {
  return Number(summary?.stars || 0);
}

function confidenceFromSummary(summary) {
  return Number(summary?.confidence || 0);
}

function pickLegFromMatch(match) {
  const s = match.prediction_summary;
  if (!s?.best_pick || s.no_bet) return null;
  const parts = String(s.best_pick).split(":");
  const market = parts.length > 1 ? parts[0].trim() : "1x2";
  const selection = parts.length > 1 ? parts.slice(1).join(":").trim() : s.best_pick;
  return {
    fixture_id: match.fixture_id || match.id,
    competition_key: match.competition_key,
    home_team: match.home_team,
    away_team: match.away_team,
    market,
    selection,
    label: s.best_pick,
    confidence: s.confidence,
    odds_decimal: match.odds_decimal || null,
    stars: s.stars,
    is_elite: s.is_elite_pick,
  };
}

export function buildCombos(matches, { maxLegs = 6 } = {}) {
  const candidates = matches
    .map((m) => ({ match: m, leg: pickLegFromMatch(m) }))
    .filter((x) => x.leg && confidenceFromSummary(x.match.prediction_summary) > 0)
    .sort((a, b) => {
      const ca = confidenceFromSummary(a.match.prediction_summary);
      const cb = confidenceFromSummary(b.match.prediction_summary);
      return cb - ca;
    });

  function assemble(targetLegs, minConf, label, risk) {
    const legs = [];
    for (const { match, leg } of candidates) {
      if (legs.length >= targetLegs) break;
      if (confidenceFromSummary(match.prediction_summary) < minConf) continue;
      if (hasConflict(legs, leg)) continue;
      legs.push({ ...leg, match });
    }
    const confs = legs.map((l) => l.confidence).filter(Boolean);
    const combinedConfidence = confs.length
      ? Math.round(confs.reduce((a, b) => a + b, 0) / confs.length)
      : null;
    const oddsList = legs.map((l) => l.odds_decimal).filter((o) => o > 1);
    const combinedOdds = oddsList.length
      ? Number(oddsList.reduce((a, b) => a * b, 1).toFixed(2))
      : null;
    return {
      id: label.toLowerCase().replace(/\s+/g, "_"),
      label,
      risk,
      legs,
      leg_count: legs.length,
      combined_confidence: combinedConfidence,
      combined_odds: combinedOdds,
    };
  }

  return [
    assemble(3, 65, "SAFE COMBO", "Low"),
    assemble(4, 55, "VALUE COMBO", "Medium"),
    assemble(Math.min(6, maxLegs), 45, "HIGH RISK", "High"),
  ].filter((c) => c.leg_count > 0);
}

export function formatStars(n) {
  const c = Math.max(0, Math.min(5, Number(n) || 0));
  return "⭐".repeat(c) + (c < 5 ? "☆".repeat(5 - c) : "");
}
