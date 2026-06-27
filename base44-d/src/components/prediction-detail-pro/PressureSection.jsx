import React from "react";
import { Gauge } from "lucide-react";

export default function PressureSection({ pressure }) {
  if (!pressure) {
    return (
      <section className="rounded-xl border border-white/[0.06] p-5 text-sm text-[#94A3B8]">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-2"><Gauge className="w-5 h-5" /> Pressure</h2>
        Pressure intelligence not available.
      </section>
    );
  }
  return (
    <section className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 space-y-3">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2"><Gauge className="w-5 h-5 text-[#FFD166]" /> Pressure</h2>
      {pressure.advantage && <p className="text-sm text-[#F8FAFC]">Advantage: <strong className="text-[#00E676]">{pressure.advantage}</strong></p>}
      {pressure.momentum && <p className="text-sm text-[#94A3B8]">Momentum: {pressure.momentum}</p>}
      {(pressure.home != null || pressure.away != null) && (
        <div className="grid grid-cols-2 gap-3 text-center text-sm">
          <div className="rounded-lg bg-black/25 p-3"><p className="text-[#64748B] text-xs">Home</p><p className="font-bold">{pressure.home ?? "—"}</p></div>
          <div className="rounded-lg bg-black/25 p-3"><p className="text-[#64748B] text-xs">Away</p><p className="font-bold">{pressure.away ?? "—"}</p></div>
        </div>
      )}
      {pressure.timeline?.length > 0 && (
        <div className="flex gap-1 items-end h-16 pt-2">
          {pressure.timeline.slice(0, 12).map((pt, i) => {
            const h = Math.max(8, Math.min(100, Number(pt.value ?? pt.pressure ?? 50)));
            return <div key={i} className="flex-1 bg-[#00E676]/40 rounded-t" style={{ height: `${h}%` }} title={pt.period || pt.minute} />;
          })}
        </div>
      )}
    </section>
  );
}
