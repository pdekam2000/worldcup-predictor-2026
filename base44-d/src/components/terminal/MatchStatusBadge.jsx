import React from "react";
import { cn } from "@/lib/utils";
import LivePulse from "./LivePulse";

const STATUS_MAP = {
  live: { label: "Live", className: "", live: true },
  "1h": { label: "Live", className: "", live: true },
  "2h": { label: "Live", className: "", live: true },
  ht: { label: "HT", className: "border-[#FFD166]/40 bg-[#FFD166]/10 text-[#FFD166]", live: true },
  ft: { label: "Finished", className: "border-white/15 bg-white/5 text-[#94A3B8]", live: false },
  finished: { label: "Finished", className: "border-white/15 bg-white/5 text-[#94A3B8]", live: false },
  ns: { label: "Upcoming", className: "border-[#3B82F6]/40 bg-[#3B82F6]/10 text-[#3B82F6]", live: false },
  upcoming: { label: "Upcoming", className: "border-[#3B82F6]/40 bg-[#3B82F6]/10 text-[#3B82F6]", live: false },
  scheduled: { label: "Upcoming", className: "border-[#3B82F6]/40 bg-[#3B82F6]/10 text-[#3B82F6]", live: false },
};

export default function MatchStatusBadge({ status, bucket }) {
  const key = String(status || bucket || "ns").toLowerCase();
  const cfg = STATUS_MAP[key] || STATUS_MAP.ns;
  if (cfg.live) return <LivePulse label={cfg.label} />;
  return (
    <span className={cn("terminal-chip", cfg.className)}>{cfg.label}</span>
  );
}
