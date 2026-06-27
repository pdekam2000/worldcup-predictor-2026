import React from "react";
import { isOwnerUser } from "@/lib/roles";
import { useAuth } from "@/lib/AuthContext";

export default function OwnerInsightOverlay({ ownerMeta }) {
  const { user } = useAuth();
  if (!isOwnerUser(user) || !ownerMeta) return null;

  const rows = [
    ["Prediction version", ownerMeta.prediction_version],
    ["Engine version", ownerMeta.engine_version],
    ["Cache age", ownerMeta.cache_age_hint],
    ["Data source", ownerMeta.data_source],
    ["API provider", ownerMeta.api_provider],
    ["Generated", ownerMeta.prediction_generated_at],
  ].filter(([, v]) => v);

  if (!rows.length) return null;

  return (
    <div className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-2 text-[10px] text-amber-200/90">
      <p className="font-semibold uppercase tracking-wider text-amber-400 mb-1">Owner insights</p>
      <dl className="space-y-0.5">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2">
            <dt className="text-amber-200/60">{k}</dt>
            <dd className="font-mono text-right truncate max-w-[55%]">{String(v)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
