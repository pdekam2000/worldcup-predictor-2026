import React from "react";
import TeamBadge from "./TeamBadge";
import { cn } from "@/lib/utils";

/**
 * Consistent home vs away row with prominent flags/logos.
 */
export default function MatchTeamsRow({
  homeTeam,
  awayTeam,
  homeLogo = null,
  awayLogo = null,
  countryHint = null,
  size = "md",
  className = "",
  center = null,
}) {
  return (
    <div className={cn("flex items-center justify-between gap-2 sm:gap-4", className)}>
      <div className="flex flex-col items-center min-w-0 flex-1">
        <TeamBadge
          teamName={homeTeam}
          logoUrl={homeLogo}
          countryHint={countryHint}
          size={size}
        />
        <span className="text-xs sm:text-sm font-semibold truncate max-w-full text-center mt-2 px-1">
          {homeTeam}
        </span>
      </div>

      <div className="flex flex-col items-center shrink-0 px-1">
        {center || (
          <span className="text-[10px] sm:text-xs font-bold uppercase tracking-widest text-muted-foreground">
            vs
          </span>
        )}
      </div>

      <div className="flex flex-col items-center min-w-0 flex-1">
        <TeamBadge
          teamName={awayTeam}
          logoUrl={awayLogo}
          countryHint={countryHint}
          size={size}
        />
        <span className="text-xs sm:text-sm font-semibold truncate max-w-full text-center mt-2 px-1">
          {awayTeam}
        </span>
      </div>
    </div>
  );
}
