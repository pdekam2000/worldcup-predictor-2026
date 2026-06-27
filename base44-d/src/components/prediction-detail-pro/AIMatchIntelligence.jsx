import React from "react";
import { Brain } from "lucide-react";

export default function AIMatchIntelligence({ insights = [] }) {
  if (!insights.length) {
    return (
      <section className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5">
        <h2 className="text-lg font-semibold flex items-center gap-2 mb-2"><Brain className="w-5 h-5 text-[#00E676]" /> AI Match Intelligence</h2>
        <p className="text-sm text-[#94A3B8]">Run or refresh prediction to populate intelligence signals.</p>
      </section>
    );
  }
  return (
    <section className="rounded-xl border border-[#00E676]/15 bg-gradient-to-br from-[#00E676]/5 to-transparent p-5 sm:p-6">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-1"><Brain className="w-5 h-5 text-[#00E676]" /> AI Match Intelligence</h2>
      <p className="text-sm text-[#94A3B8] mb-4">Why the AI recommends this prediction — from existing backend data only.</p>
      <ul className="grid sm:grid-cols-2 gap-2">
        {insights.map((tip) => (
          <li key={tip} className="flex items-start gap-2 text-sm text-[#E2E8F0] bg-black/20 rounded-lg px-3 py-2 border border-white/[0.04]">
            <span className="text-[#00E676]">✓</span> {tip}
          </li>
        ))}
      </ul>
    </section>
  );
}
