import React from "react";
import { Progress } from "@/components/ui/progress";
import { BarChart3 } from "lucide-react";

function CompareBar({ label, home, away }) {
  const h = Number(home) || 0;
  const a = Number(away) || 0;
  const max = Math.max(h, a, 1);
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-[#94A3B8]">
        <span>{label}</span>
        <span><span className="text-[#00E676]">{home ?? "—"}</span> · <span className="text-[#7DD3FC]">{away ?? "—"}</span></span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Progress value={(h / max) * 100} className="h-2 bg-white/5 [&>div]:bg-[#00E676]" />
        <Progress value={(a / max) * 100} className="h-2 bg-white/5 [&>div]:bg-[#7DD3FC]" />
      </div>
    </div>
  );
}

export default function TeamComparison({ metrics, homeTeam, awayTeam }) {
  if (!metrics?.length) {
    return (
      <section className="rounded-xl border border-white/[0.06] p-5 text-sm text-[#94A3B8]">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-2"><BarChart3 className="w-5 h-5" /> Team Comparison</h2>
        Team comparison metrics unavailable in cached payload.
      </section>
    );
  }
  return (
    <section className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 space-y-4">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2"><BarChart3 className="w-5 h-5 text-[#FFD166]" /> Team Comparison</h2>
      <div className="flex justify-between text-xs font-medium text-[#64748B] px-1">
        <span className="text-[#00E676] truncate max-w-[40%]">{homeTeam}</span>
        <span className="text-[#7DD3FC] truncate max-w-[40%] text-right">{awayTeam}</span>
      </div>
      {metrics.map((m) => (
        <CompareBar key={m.label} label={m.label} home={m.home} away={m.away} />
      ))}
    </section>
  );
}
