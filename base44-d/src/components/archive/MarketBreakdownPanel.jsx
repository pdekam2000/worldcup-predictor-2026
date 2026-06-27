import React from "react";
import { Star } from "lucide-react";

const STATUS_CLASS = {
  correct: "text-emerald-700 border-emerald-300 bg-emerald-50",
  wrong: "text-red-700 border-red-300 bg-red-50",
  pending: "text-amber-700 border-amber-300 bg-amber-50",
  unavailable: "text-slate-500 border-slate-200 bg-slate-50",
};

export function MarketBreakdownPanel({ rows = [], compact = false }) {
  if (!rows.length) return null;

  return (
    <div className={`space-y-2 ${compact ? "" : "mt-3"}`}>
      {rows.map((row) => {
        const status = String(row.status || "pending").toLowerCase();
        const cls = STATUS_CLASS[status] || STATUS_CLASS.pending;
        return (
          <div
            key={row.market_key}
            className={`flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 rounded-lg border px-3 py-2 text-sm ${cls}`}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-medium">{row.market_label || row.market_key}</span>
              {row.was_best_bet && (
                <span className="inline-flex items-center gap-0.5 text-[10px] uppercase tracking-wide font-semibold text-amber-800 bg-amber-100 border border-amber-300 px-1.5 py-0.5 rounded">
                  <Star className="w-3 h-3" /> Best bet
                </span>
              )}
            </div>
            <div className="text-xs sm:text-sm">
              <span className="opacity-80">Predicted:</span>{" "}
              <span className="font-semibold">{row.display_pick || row.predicted_pick || "—"}</span>
              <span className="mx-2 opacity-40">→</span>
              <span className="capitalize font-semibold">{status}</span>
              {row.confidence != null && (
                <span className="ml-2 opacity-70 tabular-nums">({Math.round(Number(row.confidence))}%)</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default MarketBreakdownPanel;
