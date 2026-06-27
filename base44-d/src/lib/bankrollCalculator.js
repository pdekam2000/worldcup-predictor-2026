/** Bankroll stake helpers — Phase A17 (mirrors backend profiles) */

export const BANKROLL_PRESETS = [20, 50, 100, 500];

export const RISK_PROFILES = {
  conservative: { single: [0.5, 1], combo: [0.5, 2], label: "Conservative" },
  balanced: { single: [1, 2], combo: [1, 4], label: "Balanced" },
  aggressive: { single: [2, 4], combo: [2, 8], label: "Aggressive" },
};

export function stakePctForQuality(quality, minPct, maxPct) {
  const q = Math.max(0, Math.min(100, Number(quality) || 0));
  return minPct + (q / 100) * (maxPct - minPct);
}

export function recommendStake(bankroll, { profile = "balanced", quality = 50, isCombo = false } = {}) {
  const prof = RISK_PROFILES[profile] || RISK_PROFILES.balanced;
  const range = isCombo ? prof.combo : prof.single;
  const pct = stakePctForQuality(quality, range[0] / 100, range[1] / 100);
  const stake = Math.round(bankroll * pct * 100) / 100;
  return {
    recommended_stake: stake,
    stake_pct: Math.round(pct * 10000) / 100,
    stake_range_pct: range,
  };
}

export function formatCurrency(amount, symbol = "€") {
  if (amount == null || Number.isNaN(Number(amount))) return "—";
  return `${symbol}${Number(amount).toFixed(2)}`;
}
