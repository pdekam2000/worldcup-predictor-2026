import React, { useState } from "react";
import { ChevronDown, ChevronUp, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { qualityColorClass } from "@/lib/betQualityOverlay";

function evalBorderClass(status) {
  if (status === "correct") return "border-emerald-500/50 bg-emerald-500/5";
  if (status === "wrong") return "border-red-500/50 bg-red-500/5";
  if (status === "partial") return "border-violet-500/50 bg-violet-500/5";
  if (status === "pending") return "border-yellow-500/30 bg-yellow-500/5";
  return "border-white/[0.05] bg-black/20";
}

function MarketCard({ market, onAdd }) {
  if (market.unavailable) {
    return (
      <div className="rounded-lg border border-white/[0.05] bg-black/10 p-3 opacity-70">
        <p className="text-sm font-medium text-[#94A3B8]">{market.title}</p>
        <p className="text-xs text-[#64748B] mt-1">Unavailable — {market.unavailableReason || "not in payload"}</p>
      </div>
    );
  }
  return (
    <div className={`rounded-lg border p-3 ${evalBorderClass(market.evaluationStatus)}`}>
      <div className="flex justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-white">{market.selection}</p>
          {market.evaluationStatus && (
            <p className={`text-[10px] uppercase tracking-wide mt-1 ${
              market.evaluationStatus === "correct"
                ? "text-emerald-400"
                : market.evaluationStatus === "wrong"
                  ? "text-red-400"
                  : market.evaluationStatus === "partial"
                    ? "text-violet-400"
                    : "text-yellow-500"
            }`}>
              {market.evaluationStatus}
            </p>
          )}
          <div className="flex flex-wrap gap-2 mt-1 text-[11px] text-[#94A3B8]">
            {market.probability != null && <span>Prob {market.probability}%</span>}
            {market.confidence != null && <span>Conf {market.confidence}%</span>}
            {market.betQualityScore != null && (
              <span className={`px-1.5 py-0.5 rounded border ${qualityColorClass(market.betQualityColor)}`}>
                Quality {market.betQualityScore} · {market.betQualityTier}
              </span>
            )}
            {market.risk && <span>Risk {market.risk}</span>}
          </div>
          {market.reason && <p className="text-[11px] text-[#64748B] mt-1">{market.reason}</p>}
          {market.internalStatus && (
            <p className="text-[10px] text-[#FFD166] mt-1">Internal: {market.internalStatus}</p>
          )}
        </div>
        <Button type="button" size="sm" variant="ghost" className="shrink-0" onClick={onAdd} disabled={!market.selection}>
          <Plus className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}

export default function PredictionMarketsPro({ groups, match, onAddLeg }) {
  const [openGroup, setOpenGroup] = useState(groups[0]?.id || "winner");
  if (!groups?.length) {
    return <p className="text-sm text-[#94A3B8]">No detailed markets in cached prediction.</p>;
  }

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold text-[#F8FAFC]">Prediction Markets</h2>
      <div className="flex flex-wrap gap-2">
        {groups.map((g) => (
          <button
            key={g.id}
            type="button"
            onClick={() => setOpenGroup(g.id)}
            className={`px-3 py-1.5 rounded-lg text-xs border transition-colors ${
              openGroup === g.id ? "bg-[#3B82F6] text-white border-[#3B82F6]" : "bg-white/[0.04] text-[#94A3B8] border-white/[0.06]"
            }`}
          >
            {g.label}
          </button>
        ))}
      </div>
      {groups.map((g) =>
        openGroup === g.id ? (
          <div key={g.id} className="space-y-2 animate-in fade-in duration-200">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-[#94A3B8]">{g.label}</h3>
              <span className="text-[10px] text-[#64748B]">{g.markets.length} markets</span>
            </div>
            {g.markets.map((m) => (
              <MarketCard
                key={`${g.id}-${m.title}-${m.selection}`}
                market={m}
                onAdd={() =>
                  onAddLeg({
                    fixture_id: match.fixture_id,
                    competition_key: match.competition_key,
                    home_team: match.home_team,
                    away_team: match.away_team,
                    market: m.market,
                    selection: m.raw,
                    label: `${m.title}: ${m.selection}`,
                    confidence: m.confidence,
                  })
                }
              />
            ))}
          </div>
        ) : null
      )}
    </section>
  );
}
