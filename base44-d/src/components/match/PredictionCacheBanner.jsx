import React, { useEffect, useState } from "react";
import { Clock, HardDrive, Zap } from "lucide-react";

function formatTimestamp(epochSeconds) {
  if (!epochSeconds) return null;
  const ms = epochSeconds > 1e12 ? epochSeconds : epochSeconds * 1000;
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return null;
  }
}

export default function PredictionCacheBanner({
  cacheSource,
  cachedAt = null,
  refreshCooldownRemaining = null,
  refreshCooldownSeconds = null,
}) {
  const [cooldown, setCooldown] = useState(refreshCooldownRemaining);

  useEffect(() => {
    setCooldown(refreshCooldownRemaining);
  }, [refreshCooldownRemaining]);

  useEffect(() => {
    if (cooldown == null || cooldown <= 0) return undefined;
    const timer = setInterval(() => {
      setCooldown((prev) => (prev != null && prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  const isLive = cacheSource === "live";
  const isCached = cacheSource === "cache";
  const updatedLabel = formatTimestamp(cachedAt);

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {isLive && (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-primary/10 text-primary border border-primary/20">
          <Zap className="w-3.5 h-3.5" />
          Live prediction
        </span>
      )}
      {isCached && (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/5 text-muted-foreground border border-white/10">
          <HardDrive className="w-3.5 h-3.5" />
          Cached prediction
        </span>
      )}
      {updatedLabel && (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/5 text-muted-foreground">
          <Clock className="w-3.5 h-3.5" />
          Updated {updatedLabel}
        </span>
      )}
      {cooldown != null && cooldown > 0 && (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
          <Clock className="w-3.5 h-3.5" />
          Refresh in {cooldown}s
        </span>
      )}
      {refreshCooldownSeconds != null && (cooldown == null || cooldown <= 0) && isCached && (
        <span className="text-muted-foreground/70">
          Cooldown: {refreshCooldownSeconds}s
        </span>
      )}
    </div>
  );
}
