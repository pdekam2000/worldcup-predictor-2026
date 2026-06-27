/** Combo slip builder — Phase A10 + A16 market-quality gates. */



import {

  COMBO_QUALITY_THRESHOLDS,

  betQualityFromSummary,

  isCautionPick,

  isComboEligible,

  publicPickLabel,

} from "@/lib/betQualityOverlay";



const CONFLICT_GROUPS = [

  ["home_win", "home", "away_win", "away", "draw", "1", "2", "x"],

  ["over_2_5", "under_2_5", "over_1_5", "under_1_5", "over", "under"],

  ["yes", "no", "btts_yes", "btts_no"],

];



function normSel(v) {

  return String(v || "").toLowerCase().replace(/\s+/g, "_");

}



function hasConflict(existing, candidate) {

  const cSel = normSel(candidate.selection);

  for (const leg of existing) {

    const lSel = normSel(leg.selection);

    const sameFixture = leg.fixture_id === candidate.fixture_id;

    if (sameFixture) {

      for (const group of CONFLICT_GROUPS) {

        if (group.includes(cSel) && group.includes(lSel) && cSel !== lSel) {

          return true;

        }

      }

    }

    if (

      sameFixture &&

      normSel(leg.market) === normSel(candidate.market) &&

      lSel !== cSel

    ) {

      return true;

    }

  }

  return false;

}



function isCorrelated(existing, candidate) {

  const sameLeague = existing.filter(

    (l) => l.competition_key && l.competition_key === candidate.competition_key

  );

  if (sameLeague.length >= 4) return true;

  const sameFixtureMarket = existing.some(

    (l) =>

      l.fixture_id === candidate.fixture_id &&

      normSel(l.market) === normSel(candidate.market)

  );

  return sameFixtureMarket;

}



function confidenceFromSummary(summary) {

  return Number(summary?.confidence || 0);

}



function aiScore(match) {

  return Number(match?.ai_match_score?.score || 0);

}



function valueScore(summary) {

  const v = String(summary?.value_rating || "").toUpperCase();

  if (v === "A+" || v === "A" || v === "ELITE") return 4;

  if (v === "B" || v === "STRONG") return 3;

  if (v === "C" || v === "GOOD") return 2;

  return 1;

}



function qualityScore(summary) {

  const q = betQualityFromSummary(summary);

  return Number(q?.score || 0);

}



function pickLegFromMatch(match) {

  const s = match.prediction_summary;

  const label = publicPickLabel(s);

  if (!label) return null;

  if (!isComboEligible(s, COMBO_QUALITY_THRESHOLDS.high_odds)) return null;

  if (aiScore(match) < 50 && qualityScore(s) < COMBO_QUALITY_THRESHOLDS.high_odds) return null;

  const parts = String(label).split(":");

  const market = parts.length > 1 ? parts[0].trim() : "1x2";

  const selection = parts.length > 1 ? parts.slice(1).join(":").trim() : label;

  const q = betQualityFromSummary(s);

  return {

    fixture_id: match.fixture_id || match.id,

    competition_key: match.competition_key,

    home_team: match.home_team,

    away_team: match.away_team,

    market,

    selection,

    label,

    confidence: s.confidence,

    bet_quality_score: q?.score,

    bet_quality_tier: q?.tier,

    caution: isCautionPick(s),

    odds_decimal: match.odds_decimal || estimateOdds(s.confidence),

    odds_estimated: !match.odds_decimal,

    stars: s.stars,

    is_elite: s.is_elite_pick,

    ai_score: aiScore(match),

    value_score: valueScore(s),

    readiness: comboReadiness(s),

  };

}



function estimateOdds(confidence) {

  const c = Number(confidence);

  if (!c || c <= 0) return null;

  return Number((100 / c).toFixed(2));

}



export function buildCombos(matches, { maxLegs = 6 } = {}) {

  const candidates = matches

    .map((m) => ({ match: m, leg: pickLegFromMatch(m) }))

    .filter((x) => x.leg)

    .sort((a, b) => {

      const qb = qualityScore(b.match.prediction_summary);

      const qa = qualityScore(a.match.prediction_summary);

      if (qb !== qa) return qb - qa;

      return confidenceFromSummary(b.match.prediction_summary) - confidenceFromSummary(a.match.prediction_summary);

    });



  function assemble({ targetLegs, minQuality, label, risk, sortFn }) {

    const sorted = [...candidates].sort(sortFn);

    const legs = [];

    for (const { match, leg } of sorted) {

      if (legs.length >= targetLegs) break;

      if (qualityScore(match.prediction_summary) < minQuality) continue;

      if (hasConflict(legs, leg)) continue;

      if (isCorrelated(legs, leg)) continue;

      legs.push({ ...leg, match });

    }

    const confs = legs.map((l) => l.confidence).filter(Boolean);

    const combinedConfidence = confs.length

      ? Math.round(confs.reduce((a, b) => a + b, 0) / confs.length)

      : null;

    const qualityScores = legs.map((l) => l.bet_quality_score).filter((v) => v != null);

    const combinedQuality = qualityScores.length

      ? Math.round(qualityScores.reduce((a, b) => a + b, 0) / qualityScores.length)

      : null;

    const oddsList = legs.map((l) => l.odds_decimal).filter((o) => o > 1);

    const combinedOdds = oddsList.length

      ? Number(oddsList.reduce((a, b) => a * b, 1).toFixed(2))

      : null;

    const hasCaution = legs.some((l) => l.caution);

    return {

      id: label.toLowerCase().replace(/\s+/g, "_"),

      label,

      risk,

      legs,

      leg_count: legs.length,

      combined_confidence: combinedConfidence,

      combined_quality: combinedQuality,

      combined_odds: combinedOdds,

      caution_warning: hasCaution ? "Includes caution — best available legs" : null,

    };

  }



  return [

    assemble({

      targetLegs: 3,

      minQuality: COMBO_QUALITY_THRESHOLDS.safe,

      label: "SAFE COMBO",

      risk: "Low",

      sortFn: (a, b) => qualityScore(b.match.prediction_summary) - qualityScore(a.match.prediction_summary),

    }),

    assemble({

      targetLegs: 4,

      minQuality: COMBO_QUALITY_THRESHOLDS.balanced,

      label: "BALANCED COMBO",

      risk: "Medium",

      sortFn: (a, b) => aiScore(b.match) - aiScore(a.match),

    }),

    assemble({

      targetLegs: 4,

      minQuality: COMBO_QUALITY_THRESHOLDS.value,

      label: "HIGH VALUE",

      risk: "Medium",

      sortFn: (a, b) => valueScore(b.match.prediction_summary) - valueScore(a.match.prediction_summary),

    }),

    assemble({

      targetLegs: Math.min(5, maxLegs),

      minQuality: COMBO_QUALITY_THRESHOLDS.high_odds,

      label: "HIGH ODDS",

      risk: "High",

      sortFn: (a, b) => (b.leg.odds_decimal || 0) - (a.leg.odds_decimal || 0),

    }),

  ].filter((c) => c.leg_count > 0);

}



export function formatStars(n) {

  const c = Math.max(0, Math.min(5, Number(n) || 0));

  return "⭐".repeat(c) + (c < 5 ? "☆".repeat(5 - c) : "");

}



/** Combo readiness from market quality (Phase A16). */

export function comboReadiness(summary) {

  if (!summary) return { status: "waiting", label: "Waiting for prediction" };

  const q = betQualityFromSummary(summary);

  if (q?.status === "unavailable") {

    return { status: "unavailable", label: q.reason || "Prediction unavailable" };

  }

  if (!publicPickLabel(summary)) return { status: "waiting", label: "Waiting for prediction" };

  if (isCautionPick(summary)) {

    return { status: "caution", label: "Caution — Best Available" };

  }

  if (isComboEligible(summary, COMBO_QUALITY_THRESHOLDS.high_odds)) {

    return { status: "ready", label: `Ready · Quality ${q?.score ?? "—"}` };

  }

  return { status: "low_quality", label: `Quality below ${COMBO_QUALITY_THRESHOLDS.high_odds}` };

}



export function comboEmptyReason(matches) {

  const total = matches.length;

  const withPick = matches.filter((m) => publicPickLabel(m.prediction_summary)).length;

  const eligible = matches.filter((m) =>

    isComboEligible(m.prediction_summary, COMBO_QUALITY_THRESHOLDS.high_odds)

  ).length;

  const caution = matches.filter((m) => isCautionPick(m.prediction_summary)).length;

  if (!total) return "No fixtures loaded";

  if (!withPick) return `No market picks available (${total} fixtures)`;

  if (!eligible) {

    return `No legs meet quality ≥${COMBO_QUALITY_THRESHOLDS.high_odds} (${withPick} with picks, ${caution} caution)`;

  }

  return null;

}


