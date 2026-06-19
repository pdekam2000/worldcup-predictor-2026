import React from "react";
import { resolveTeamVisual } from "@/lib/teamFlags";

/**
 * Team avatar: API-Football logo when available, else flag CDN, else initials.
 */
export default function TeamBadge({
  teamName,
  logoUrl = null,
  countryHint = null,
  size = "md",
  className = "",
}) {
  const visual = resolveTeamVisual(teamName, { logoUrl, countryHint });
  const sizeClasses = size === "lg" ? "w-16 h-16 sm:w-20 sm:h-20 text-xl" : "w-12 h-12 text-sm";
  const imgSrc = visual.logoUrl || visual.flagUrl;

  return (
    <div
      className={`mx-auto rounded-xl bg-white/5 flex items-center justify-center overflow-hidden mb-2 font-bold text-primary ${sizeClasses} ${className}`}
      title={teamName}
    >
      {imgSrc ? (
        <img
          src={imgSrc}
          alt={teamName}
          className="w-full h-full object-contain p-1.5"
          loading="lazy"
          onError={(e) => {
            e.currentTarget.style.display = "none";
            const fallback = e.currentTarget.nextElementSibling;
            if (fallback) fallback.style.display = "flex";
          }}
        />
      ) : null}
      <span
        className={`items-center justify-center w-full h-full ${imgSrc ? "hidden" : "flex"}`}
        style={imgSrc ? { display: "none" } : undefined}
      >
        {visual.initials}
      </span>
    </div>
  );
}
