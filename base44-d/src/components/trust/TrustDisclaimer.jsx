import React from "react";
import { AlertTriangle } from "lucide-react";
import {
  TRUST_RESEARCH_ONLY,
  TRUST_WINRATE_BEST_BETS,
  TRUST_NO_BET,
} from "@/lib/trustCopy";

/**
 * Compact trust strip — use on landing, dashboard pages, and prediction surfaces.
 * @param {"inline"|"stack"|"compact"} variant
 */
export default function TrustDisclaimer({ variant = "stack", className = "" }) {
  const lines =
    variant === "compact"
      ? [TRUST_RESEARCH_ONLY]
      : [TRUST_RESEARCH_ONLY, TRUST_WINRATE_BEST_BETS, TRUST_NO_BET];

  if (variant === "inline") {
    return (
      <p className={`text-xs text-muted-foreground ${className}`}>
        {lines.join(" · ")}
      </p>
    );
  }

  return (
    <div
      className={`rounded-xl border border-amber-200/70 bg-amber-50/50 p-4 flex gap-3 items-start ${className}`}
    >
      <AlertTriangle className="w-4 h-4 text-amber-700 flex-shrink-0 mt-0.5" />
      <ul className="text-xs text-slate-600 space-y-1">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </div>
  );
}
