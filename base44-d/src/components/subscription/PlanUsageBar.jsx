import React from "react";
import { Zap } from "lucide-react";

export default function PlanUsageBar({ used, limit, remaining, percent, bypass }) {
  if (bypass) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm text-muted-foreground flex items-center gap-2">
        <Zap className="w-4 h-4 text-primary" />
        Admin bypass active — unlimited predictions
      </div>
    );
  }

  if (!limit && limit !== 0) {
    return (
      <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-4 text-sm text-muted-foreground">
        Quota information is not available right now.
      </div>
    );
  }

  const pct = Math.min(100, Math.max(0, percent ?? 0));
  const barColor = pct >= 90 ? "bg-red-500" : pct >= 75 ? "bg-yellow-500" : "bg-primary";

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">Monthly prediction quota</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {used} used · {remaining} remaining · {limit} total
          </p>
        </div>
        <span className="text-sm font-semibold tabular-nums">{pct}%</span>
      </div>
      <div className="h-2.5 rounded-full bg-white/10 overflow-hidden">
        <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="flex justify-between text-[11px] text-muted-foreground">
        <span>0</span>
        <span>{limit} predictions / month</span>
      </div>
    </div>
  );
}
