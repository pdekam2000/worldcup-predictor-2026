import React from "react";
import { cn } from "@/lib/utils";

/**
 * Center divider for match cards — team vs team with soccer ball accent.
 */
export default function MatchVersusCenter({ prediction, className }) {
  const pickLabel =
    prediction === "home" ? "1" : prediction === "draw" ? "X" : prediction === "away" ? "2" : null;

  return (
    <div className={cn("flex flex-col items-center justify-center px-3 sm:px-4 shrink-0", className)}>
      <div
        className="w-10 h-10 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center text-lg shadow-sm mb-1.5"
        aria-hidden
      >
        ⚽
      </div>
      {pickLabel ? (
        <div className="text-[10px] font-semibold px-2 py-0.5 rounded bg-primary/10 text-primary uppercase tracking-wide">
          {pickLabel}
        </div>
      ) : (
        <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest">vs</div>
      )}
    </div>
  );
}
