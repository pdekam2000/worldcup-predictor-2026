import React from "react";
import { cn } from "@/lib/utils";

const TIER_STYLES = {
  A: "border-[#00E676]/50 bg-[#00E676]/15 text-[#00E676]",
  B: "border-[#3B82F6]/50 bg-[#3B82F6]/15 text-[#3B82F6]",
  C: "border-[#FFD166]/50 bg-[#FFD166]/15 text-[#FFD166]",
  D: "border-white/15 bg-white/5 text-[#94A3B8]",
};

export default function TierBadge({ tier, label, compact = false, className }) {
  if (!tier) return null;
  const style = TIER_STYLES[tier] || TIER_STYLES.D;
  return (
    <span
      className={cn("terminal-chip", style, compact && "text-[10px] px-2 py-0", className)}
      title={label ? `${label} tier ${tier}` : `Tier ${tier}`}
    >
      {label ? `${label} ` : ""}
      {tier}
    </span>
  );
}

export { TIER_STYLES };
