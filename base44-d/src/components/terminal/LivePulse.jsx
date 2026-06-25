import React from "react";
import { cn } from "@/lib/utils";

export default function LivePulse({ className, label = "LIVE" }) {
  return (
    <span
      className={cn(
        "terminal-chip border-[#FF4D4D]/40 bg-[#FF4D4D]/10 text-[#FF4D4D]",
        className
      )}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-[#FF4D4D] animate-live-pulse" />
      {label}
    </span>
  );
}
