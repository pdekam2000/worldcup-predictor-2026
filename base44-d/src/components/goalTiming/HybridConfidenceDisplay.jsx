import React from "react";

import TierBadge, { TIER_STYLES } from "@/components/terminal/TierBadge";



function ProbabilityBar({ bars }) {

  if (!bars?.length) return null;

  const max = Math.max(...bars.map((b) => b.probability || 0), 0.01);

  return (

    <div className="space-y-1.5">

      <p className="text-xs text-[#94A3B8]">Estimated timing range</p>

      {bars.map((row) => (

        <div key={row.bucket} className="flex items-center gap-2 text-xs">

          <span className="w-14 shrink-0 font-mono text-[#94A3B8]">{row.bucket}</span>

          <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">

            <div

              className="h-full rounded-full bg-gradient-to-r from-[#00E676] to-[#3B82F6]"

              style={{ width: `${Math.round(((row.probability || 0) / max) * 100)}%` }}

            />

          </div>

        </div>

      ))}

    </div>

  );

}



/**

 * Hybrid per-market confidence — tiers as primary trust signal.

 */

export default function HybridConfidenceDisplay({

  hybrid,

  compact = false,

  showLegacyNote = false,

  legacyConfidence,

}) {

  if (!hybrid) {

    if (showLegacyNote && legacyConfidence != null) {

      return (

        <p className="text-xs text-[#94A3B8]">

          Legacy confidence retained for compatibility.

        </p>

      );

    }

    return null;

  }



  const team = hybrid.team || {};

  const range = hybrid.range || {};

  const minute = hybrid.minute || {};



  if (compact) {

    return (

      <div className="flex flex-wrap items-center gap-2 text-xs">

        <TierBadge tier={team.tier} label="Team" compact />

        <TierBadge tier={range.tier} label="Range" compact />

        <span className="text-[#94A3B8]">{team.label}</span>

      </div>

    );

  }



  return (

    <div className="rounded-xl border border-white/[0.06] bg-black/20 p-3 space-y-3">

      <p className="text-xs font-medium uppercase tracking-wide text-[#94A3B8]">

        Reliability tiers

      </p>



      <div className="space-y-2">

        <div className="flex flex-wrap items-center gap-2">

          <TierBadge tier={team.tier} />

          <span className="text-sm font-medium text-[#F8FAFC]">{team.label || "Directional edge"}</span>

          {team.reliability && (

            <span className="text-xs text-[#94A3B8] capitalize">({team.reliability})</span>

          )}

        </div>

        <p className="text-xs text-[#94A3B8]">

          First-goal team reflects directional edge, not certainty.

        </p>

      </div>



      <div className="space-y-2 border-t border-white/[0.06] pt-3">

        <TierBadge tier={range.tier} label="Range" />

        <ProbabilityBar bars={range.probability_bar} />

      </div>



      <div className="space-y-1 border-t border-white/[0.06] pt-3">

        <div className="flex flex-wrap items-center gap-2">

          <span className="text-sm font-medium text-[#F8FAFC]">{minute.label || "Estimate only"}</span>

          {minute.experimental && (

            <span className="terminal-chip border-[#FFD166]/40 bg-[#FFD166]/10 text-[#FFD166]">

              {minute.badge || "Experimental"}

            </span>

          )}

          {minute.tier && <TierBadge tier={minute.tier} label="Minute" compact />}

        </div>

        <p className="text-xs text-[#94A3B8]">

          Minute estimate is experimental — not a high-confidence exact prediction.

        </p>

      </div>

    </div>

  );

}



export { TierBadge, ProbabilityBar, TIER_STYLES };


