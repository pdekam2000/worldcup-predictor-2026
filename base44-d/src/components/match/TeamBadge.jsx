import React from "react";
import { resolveTeamVisual } from "@/lib/teamFlags";
import { cn } from "@/lib/utils";

const SIZE_MAP = {
  sm: { box: "w-10 h-10", text: "text-xs", pad: "p-1", flagW: 64 },
  md: { box: "w-14 h-14 sm:w-16 sm:h-16", text: "text-sm", pad: "p-1.5", flagW: 96 },
  lg: { box: "w-20 h-20", text: "text-base", pad: "p-2", flagW: 128 },
  xl: { box: "w-20 h-20 sm:w-24 sm:h-24", text: "text-lg", pad: "p-2", flagW: 160 },
};

/**
 * Team avatar: API logo when available, else flag CDN, else initials.
 */
export default function TeamBadge({
  teamName,
  logoUrl = null,
  countryHint = null,
  size = "md",
  className = "",
  showRing = true,
}) {
  const dims = SIZE_MAP[size] || SIZE_MAP.md;
  const visual = resolveTeamVisual(teamName, { logoUrl, countryHint, flagWidth: dims.flagW });
  const imgSrc = visual.logoUrl || visual.flagUrl;

  return (
    <div
      className={cn(
        "mx-auto rounded-2xl bg-[#101827] flex items-center justify-center overflow-hidden font-bold text-[#00E676] shadow-lg shadow-black/30",
        showRing && "ring-2 ring-[#00E676]/20 ring-offset-2 ring-offset-[#070B14]",
        dims.box,
        dims.text,
        className
      )}
      title={teamName}
    >
      {imgSrc ? (
        <img
          src={imgSrc}
          alt={teamName}
          className={cn("w-full h-full object-contain", dims.pad)}
          loading="lazy"
          onError={(e) => {
            e.currentTarget.style.display = "none";
            const fallback = e.currentTarget.nextElementSibling;
            if (fallback) fallback.style.display = "flex";
          }}
        />
      ) : null}
      <span
        className={cn(
          "items-center justify-center w-full h-full bg-[#00E676]/10",
          imgSrc ? "hidden" : "flex"
        )}
      >
        {visual.initials}
      </span>
    </div>
  );
}
