import React from "react";
import { cn } from "@/lib/utils";

export default function WinrateCard({
  label,
  value,
  sub,
  icon: Icon,
  accent = "green",
  loading = false,
  className,
}) {
  const accents = {
    green: { icon: "text-[#00E676]", bg: "bg-[#00E676]/10", value: "text-[#00E676]" },
    gold: { icon: "text-[#FFD166]", bg: "bg-[#FFD166]/10", value: "text-[#FFD166]" },
    blue: { icon: "text-[#3B82F6]", bg: "bg-[#3B82F6]/10", value: "text-[#3B82F6]" },
    red: { icon: "text-[#FF4D4D]", bg: "bg-[#FF4D4D]/10", value: "text-[#FF4D4D]" },
    neutral: { icon: "text-[#94A3B8]", bg: "bg-white/5", value: "text-[#F8FAFC]" },
  };
  const a = accents[accent] || accents.green;

  return (
    <div className={cn("terminal-card p-4 sm:p-5", className)}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <span className="text-xs text-[#94A3B8] font-medium">{label}</span>
        {Icon && (
          <div className={cn("w-9 h-9 rounded-xl flex items-center justify-center", a.bg)}>
            <Icon className={cn("w-4 h-4", a.icon)} />
          </div>
        )}
      </div>
      <div className={cn("text-2xl sm:text-3xl font-display font-bold tabular-nums", a.value)}>
        {loading ? "…" : value ?? "—"}
      </div>
      {sub && <p className="text-xs text-[#94A3B8] mt-1.5">{sub}</p>}
    </div>
  );
}
