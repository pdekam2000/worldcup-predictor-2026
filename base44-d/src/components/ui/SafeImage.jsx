import React, { useState } from "react";
import { resolveSafeImageUrl, getTeamInitialsFallback } from "@/lib/imageResolver";
import { cn } from "@/lib/utils";

/**
 * Image with initials/country badge fallback — no broken-image icon.
 */
export default function SafeImage({
  src,
  alt = "",
  fallbackText = "?",
  className = "",
  imgClassName = "",
  fallbackClassName = "",
}) {
  const [failed, setFailed] = useState(false);
  const safeSrc = resolveSafeImageUrl(src);
  const showImg = safeSrc && !failed;
  const initials = getTeamInitialsFallback(fallbackText || alt);

  return (
    <div className={cn("relative flex items-center justify-center overflow-hidden", className)}>
      {showImg ? (
        <img
          src={safeSrc}
          alt={alt}
          className={cn("w-full h-full object-contain", imgClassName)}
          loading="lazy"
          onError={() => setFailed(true)}
        />
      ) : (
        <span
          className={cn(
            "flex items-center justify-center w-full h-full font-bold text-[#00E676] bg-[#00E676]/10",
            fallbackClassName
          )}
        >
          {initials}
        </span>
      )}
    </div>
  );
}
