/**
 * Bet slip state — client-side only (no backend changes).
 */
import React, { createContext, useCallback, useContext, useMemo, useState } from "react";

const BetSlipContext = createContext(null);

function legOdds(leg) {
  const o = leg?.odds_decimal ?? leg?.odds ?? leg?.implied_odds;
  if (o == null) return null;
  const n = Number(o);
  return Number.isFinite(n) && n > 1 ? n : null;
}

export function BetSlipProvider({ children }) {
  const [legs, setLegs] = useState([]);

  const addLeg = useCallback((leg) => {
    if (!leg?.fixture_id) return;
    setLegs((prev) => {
      const key = `${leg.fixture_id}:${leg.market || leg.market_id}:${leg.selection}`;
      if (prev.some((l) => `${l.fixture_id}:${l.market || l.market_id}:${l.selection}` === key)) {
        return prev;
      }
      return [...prev, { ...leg, id: key }];
    });
  }, []);

  const removeLeg = useCallback((id) => {
    setLegs((prev) => prev.filter((l) => l.id !== id));
  }, []);

  const clearSlip = useCallback(() => setLegs([]), []);

  const totalOdds = useMemo(() => {
    const withOdds = legs.map(legOdds).filter((o) => o != null);
    if (!withOdds.length) return null;
    return withOdds.reduce((acc, o) => acc * o, 1);
  }, [legs]);

  const avgConfidence = useMemo(() => {
    const vals = legs.map((l) => l.confidence).filter((c) => c != null);
    if (!vals.length) return null;
    return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length);
  }, [legs]);

  const riskRating = useMemo(() => {
    if (legs.length >= 6) return "High";
    if (legs.length >= 4) return "Medium";
    return "Low";
  }, [legs.length]);

  const value = useMemo(
    () => ({
      legs,
      addLeg,
      removeLeg,
      clearSlip,
      totalOdds,
      avgConfidence,
      riskRating,
      legCount: legs.length,
    }),
    [legs, addLeg, removeLeg, clearSlip, totalOdds, avgConfidence, riskRating]
  );

  return <BetSlipContext.Provider value={value}>{children}</BetSlipContext.Provider>;
}

export function useBetSlip() {
  const ctx = useContext(BetSlipContext);
  if (!ctx) throw new Error("useBetSlip must be used within BetSlipProvider");
  return ctx;
}
