/** Bet Quality publication overlay — Phase A16 (mirrors backend tiers). */

export const QUALITY_TIERS = [
  { min: 95, tier: "Elite", color: "dark_green" },
  { min: 85, tier: "Excellent", color: "green" },
  { min: 75, tier: "Strong", color: "light_green" },
  { min: 60, tier: "Good", color: "yellow" },
  { min: 45, tier: "Medium Risk", color: "orange" },
  { min: 25, tier: "High Risk", color: "red" },
  { min: 0, tier: "Very Weak", color: "dark_red" },
];

export const COMBO_QUALITY_THRESHOLDS = {
  safe: 90,
  balanced: 75,
  value: 60,
  high_odds: 45,
};

export const QUALITY_COLOR_CLASS = {
  dark_green: "text-[#00C853] border-[#00C853]/40 bg-[#00C853]/10",
  green: "text-[#00E676] border-[#00E676]/40 bg-[#00E676]/10",
  light_green: "text-[#7DD3A0] border-[#7DD3A0]/40 bg-[#7DD3A0]/10",
  yellow: "text-[#FFD166] border-[#FFD166]/40 bg-[#FFD166]/10",
  orange: "text-[#FF9F43] border-[#FF9F43]/40 bg-[#FF9F43]/10",
  red: "text-[#FF6B6B] border-[#FF6B6B]/40 bg-[#FF6B6B]/10",
  dark_red: "text-[#C62828] border-[#C62828]/40 bg-[#C62828]/10",
};

export function tierFromScore(score) {
  const s = Math.max(0, Math.min(100, Number(score) || 0));
  for (const band of QUALITY_TIERS) {
    if (s >= band.min) {
      return { bet_quality_score: Math.round(s * 10) / 10, bet_quality_tier: band.tier, bet_quality_color: band.color };
    }
  }
  return { bet_quality_score: s, bet_quality_tier: "Very Weak", bet_quality_color: "dark_red" };
}

export function qualityColorClass(color) {
  return QUALITY_COLOR_CLASS[color] || QUALITY_COLOR_CLASS.yellow;
}

export function betQualityFromSummary(summary) {
  if (!summary) return null;
  const overlay = summary.publication_overlay || {};
  return {
    score: summary.bet_quality_score ?? overlay.bet_quality_score,
    tier: summary.bet_quality_tier ?? overlay.bet_quality_tier,
    color: summary.bet_quality_color ?? overlay.bet_quality_color,
    status: overlay.public_recommendation_status ?? summary.display_status,
    cautionLabel: summary.caution_label ?? overlay.caution_label,
    reason: overlay.quality_reason ?? summary.unavailable_reason,
    derivedFromNoBet: overlay.derived_from_no_bet_fixture,
  };
}

export function isComboEligible(summary, minQuality = 45) {
  const q = betQualityFromSummary(summary);
  if (!q) return false;
  if (q.status === "unavailable") return false;
  const score = Number(q.score) || 0;
  if (score < minQuality) return false;
  return Boolean(summary?.best_pick || summary?.publication_overlay?.public_best_pick);
}

export function publicPickLabel(summary) {
  if (!summary) return null;
  if (summary.best_pick) return summary.best_pick;
  return summary.publication_overlay?.public_best_pick || null;
}

export function isCautionPick(summary) {
  const q = betQualityFromSummary(summary);
  return q?.status === "caution_best_available" || Boolean(summary?.caution_label);
}
