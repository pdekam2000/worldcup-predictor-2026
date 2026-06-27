import React from "react";
import { HelpCircle } from "lucide-react";
import { Progress } from "@/components/ui/progress";

export default function ConfidenceExplanation({ explanation }) {
  if (!explanation) return null;
  const { confidence, factors, gap, cautionReason } = explanation;
  return (
    <section className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 space-y-4">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2">
        <HelpCircle className="w-5 h-5 text-[#7DD3FC]" /> Confidence Explanation
      </h2>
      <p className="text-sm text-[#94A3B8]">
        Model confidence is <strong className="text-white text-lg">{confidence}%</strong> — here is how contributing factors shape that score.
      </p>
      {cautionReason && <p className="text-xs text-[#FFD166]">{cautionReason}</p>}
      {gap != null && gap > 0 && <p className="text-xs text-[#64748B]">Gap to premium threshold: {gap} points</p>}
      <div className="space-y-3">
        {factors.map((f) => (
          <div key={f.label}>
            <div className="flex justify-between text-xs text-[#94A3B8] mb-1">
              <span>{f.label}</span>
              <span>{f.score}% · weight {f.weight}%</span>
            </div>
            <Progress value={f.weight} className="h-2 bg-white/5" />
          </div>
        ))}
      </div>
      <p className="text-[10px] text-[#64748B] italic">
        Confidence measures model trust in the recommendation — not the same as outcome probability.
      </p>
    </section>
  );
}
