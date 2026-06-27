import React from "react";
import { Activity } from "lucide-react";

export default function ExpectedGoalsSection({ xg, homeTeam, awayTeam }) {
  if (!xg) {
    return (
      <section className="rounded-xl border border-white/[0.06] p-5 text-sm text-[#94A3B8]">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-2"><Activity className="w-5 h-5" /> Expected Goals</h2>
        xG data not available for this fixture.
      </section>
    );
  }
  return (
    <section className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4"><Activity className="w-5 h-5 text-[#00E676]" /> Expected Goals</h2>
      <div className="grid grid-cols-3 gap-4 text-center">
        <div>
          <p className="text-[10px] uppercase text-[#64748B] truncate">{homeTeam}</p>
          <p className="text-3xl font-bold text-[#00E676]">{xg.home ?? "—"}</p>
          <p className="text-[10px] text-[#64748B]">Home xG</p>
        </div>
        <div>
          <p className="text-[10px] uppercase text-[#64748B]">Difference</p>
          <p className={`text-3xl font-bold ${(xg.difference || 0) > 0 ? "text-[#00E676]" : (xg.difference || 0) < 0 ? "text-[#7DD3FC]" : "text-white"}`}>
            {xg.difference != null ? (xg.difference > 0 ? `+${xg.difference}` : xg.difference) : "—"}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase text-[#64748B] truncate">{awayTeam}</p>
          <p className="text-3xl font-bold text-[#7DD3FC]">{xg.away ?? "—"}</p>
          <p className="text-[10px] text-[#64748B]">Away xG</p>
        </div>
      </div>
      {xg.trend && <p className="text-xs text-[#94A3B8] mt-4 text-center">Trend: {typeof xg.trend === "object" ? JSON.stringify(xg.trend) : xg.trend}</p>}
    </section>
  );
}
