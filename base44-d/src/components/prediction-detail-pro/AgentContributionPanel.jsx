import React from "react";
import { Cpu } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { isAdminUser, isOwnerUser } from "@/lib/roles";

export default function AgentContributionPanel({ agents }) {
  const { user } = useAuth();
  if (!isOwnerUser(user) && !isAdminUser(user)) return null;

  return (
    <section className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-5">
      <h2 className="text-lg font-semibold text-amber-200 flex items-center gap-2 mb-3"><Cpu className="w-5 h-5" /> Agent Contribution</h2>
      <p className="text-xs text-amber-200/60 mb-4">Owner/Admin only — read-only specialist trace from cached prediction.</p>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {agents.map((a) => (
          <div key={a.key} className="rounded-lg bg-black/30 border border-amber-500/20 p-3 text-xs">
            <p className="font-semibold text-amber-100">{a.title}</p>
            <p className="text-amber-200/70 mt-1">Status: {a.status}</p>
            {a.impact != null && <p className="text-amber-200/70">Impact: {a.impact}%</p>}
            {a.domain && <p className="text-amber-200/50 truncate">{a.domain}</p>}
          </div>
        ))}
      </div>
    </section>
  );
}
