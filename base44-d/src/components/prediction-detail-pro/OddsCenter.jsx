import React from "react";
import { LineChart, TrendingUp, TrendingDown } from "lucide-react";

export default function OddsCenter({ odds }) {
  if (!odds || (!odds.homeWin && !odds.current)) {
    return (
      <section className="rounded-xl border border-white/[0.06] p-5 text-sm text-[#94A3B8]">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-2"><LineChart className="w-5 h-5" /> Odds Center</h2>
        Bookmaker odds not attached to this cached prediction.
      </section>
    );
  }
  const movement = odds.movement;
  return (
    <section className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 space-y-4">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2"><LineChart className="w-5 h-5 text-[#7DD3FC]" /> Odds Center</h2>
      <div className="grid grid-cols-3 gap-3 text-center">
        {[
          ["Home", odds.homeWin],
          ["Draw", odds.draw],
          ["Away", odds.awayWin],
        ].map(([label, val]) => (
          <div key={label} className="rounded-lg bg-black/25 p-3 border border-white/[0.04]">
            <p className="text-[10px] uppercase text-[#64748B]">{label}</p>
            <p className="text-lg font-bold text-white">{val != null ? `${typeof val === "number" && val <= 1 ? Math.round(val * 100) : val}${typeof val === "number" && val <= 1 ? "%" : ""}` : "—"}</p>
            <p className="text-[10px] text-[#64748B]">Implied</p>
          </div>
        ))}
      </div>
      {odds.valueIndicator && (
        <p className="text-sm text-[#FFD166]">Value indicator: <strong>{odds.valueIndicator}</strong></p>
      )}
      {movement && (
        <p className="text-xs text-[#94A3B8] flex items-center gap-2">
          {String(movement).toLowerCase().includes("up") ? <TrendingUp className="w-4 h-4 text-[#00E676]" /> : <TrendingDown className="w-4 h-4 text-red-400" />}
          Odds movement: {typeof movement === "object" ? JSON.stringify(movement) : movement}
        </p>
      )}
      {odds.consensus && <p className="text-xs text-[#64748B]">Bookmaker consensus: {odds.consensus} sources</p>}
    </section>
  );
}
