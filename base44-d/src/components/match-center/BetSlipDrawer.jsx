import React, { useState } from "react";
import { X, Copy, Trash2, Receipt } from "lucide-react";
import { useBetSlip } from "@/context/BetSlipContext";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function BetSlipDrawer({ className }) {
  const { legs, removeLeg, clearSlip, totalOdds, avgConfidence, riskRating, legCount } = useBetSlip();
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!legCount && !open) {
    return null;
  }

  const slipText = legs
    .map((l, i) => `${i + 1}. ${l.home_team} vs ${l.away_team} — ${l.label || l.selection}`)
    .join("\n");

  const copySlip = async () => {
    const body = [
      "WorldCup Predictor — Combo Slip",
      "Research only — not betting advice.",
      "",
      slipText,
      "",
      `Legs: ${legCount}`,
      totalOdds ? `Combined odds: ${totalOdds.toFixed(2)}` : "Combined odds: n/a",
      avgConfidence ? `Avg confidence: ${avgConfidence}%` : "",
      `Risk: ${riskRating}`,
    ].filter(Boolean).join("\n");
    try {
      await navigator.clipboard.writeText(body);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 px-4 py-3 rounded-2xl",
          "bg-[#00E676] text-[#0B1220] font-semibold shadow-[0_8px_32px_rgba(0,230,118,0.35)] hover:bg-[#00E676]/90 transition-all",
          className
        )}
      >
        <Receipt className="w-5 h-5" />
        Bet Slip ({legCount})
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <button type="button" className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} aria-label="Close bet slip" />
          <aside className="relative w-full max-w-md h-full bg-[#0B1220] border-l border-white/10 shadow-2xl flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-white/10">
              <h2 className="text-lg font-semibold text-[#FFD166]">Bet Slip</h2>
              <button type="button" onClick={() => setOpen(false)} className="text-[#94A3B8] hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {legs.length === 0 ? (
                <p className="text-sm text-[#94A3B8]">Add picks from match cards or combo tips.</p>
              ) : (
                legs.map((leg) => (
                  <div key={leg.id} className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-3">
                    <div className="flex justify-between gap-2">
                      <div>
                        <p className="text-xs text-[#64748B]">{leg.home_team} vs {leg.away_team}</p>
                        <p className="text-sm font-medium text-[#F8FAFC]">{leg.label || leg.selection}</p>
                        {leg.confidence != null && (
                          <p className="text-[11px] text-[#94A3B8] mt-1">Confidence {Math.round(leg.confidence)}%</p>
                        )}
                      </div>
                      <button type="button" onClick={() => removeLeg(leg.id)} className="text-[#94A3B8] hover:text-red-400">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="p-4 border-t border-white/10 space-y-3 bg-[#101827]/80">
              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-lg bg-white/[0.04] p-2">
                  <p className="text-[#64748B]">Legs</p>
                  <p className="text-lg font-bold text-white">{legCount}</p>
                </div>
                <div className="rounded-lg bg-white/[0.04] p-2">
                  <p className="text-[#64748B]">Odds</p>
                  <p className="text-lg font-bold text-[#FFD166]">{totalOdds ? totalOdds.toFixed(2) : "—"}</p>
                </div>
                <div className="rounded-lg bg-white/[0.04] p-2">
                  <p className="text-[#64748B]">Risk</p>
                  <p className="text-lg font-bold text-white">{riskRating}</p>
                </div>
              </div>
              {avgConfidence != null && (
                <p className="text-xs text-[#94A3B8] text-center">Avg confidence {avgConfidence}%</p>
              )}
              <p className="text-[10px] text-center text-[#64748B] italic">Research only — not betting advice.</p>
              <div className="flex gap-2">
                <Button type="button" variant="outline" className="flex-1 border-white/10" onClick={clearSlip} disabled={!legCount}>
                  Clear
                </Button>
                <Button type="button" className="flex-1 bg-[#00E676] text-[#0B1220] hover:bg-[#00E676]/90" onClick={copySlip} disabled={!legCount}>
                  <Copy className="w-4 h-4 mr-1" /> {copied ? "Copied" : "Copy Slip"}
                </Button>
              </div>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
