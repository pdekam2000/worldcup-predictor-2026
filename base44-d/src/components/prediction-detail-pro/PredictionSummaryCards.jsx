import React from "react";

import { Target, Percent, TrendingUp, AlertTriangle, DollarSign, Users, Shield } from "lucide-react";

import { Progress } from "@/components/ui/progress";

import { qualityColorClass } from "@/lib/betQualityOverlay";



function Card({ icon: Icon, label, value, sub, accent = "text-[#F8FAFC]" }) {

  return (

    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 hover:border-white/10 transition-colors">

      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-[#64748B] mb-2">

        <Icon className="w-3.5 h-3.5" /> {label}

      </div>

      <p className={`text-xl sm:text-2xl font-bold ${accent}`}>{value != null && typeof value === "object" ? "—" : (value ?? "—")}</p>

      {sub != null && <p className="text-xs text-[#94A3B8] mt-1">{sub}</p>}

      {typeof value === "number" && label === "Confidence" && (

        <Progress value={value} className="h-1.5 mt-3 bg-white/10" />

      )}

    </div>

  );

}



export default function PredictionSummaryCards({ summary }) {

  if (!summary) return null;

  const caution = summary.caution || summary.cautionLabel;

  return (

    <section className="space-y-3">

      <h2 className="text-lg font-semibold text-[#F8FAFC]">Prediction Summary</h2>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">

        <div className={`col-span-2 lg:col-span-2 rounded-xl border p-4 ${caution ? "border-[#FF9F43]/25 bg-[#FF9F43]/5" : "border-[#00E676]/25 bg-[#00E676]/5"}`}>

          <p className={`text-[10px] uppercase mb-1 flex items-center gap-1 ${caution ? "text-[#FF9F43]" : "text-[#00E676]"}`}>

            <Target className="w-3.5 h-3.5" /> {caution ? summary.cautionLabel || "Caution — Best Available" : "Best Pick"}

          </p>

          <p className="text-2xl font-bold text-white">
            {typeof summary.bestPick === "object" ? "—" : (summary.bestPick || (summary.unavailableReason ? "Prediction unavailable" : "—"))}
          </p>

          {summary.unavailableReason && <p className="text-xs text-[#94A3B8] mt-1">{summary.unavailableReason}</p>}

          {summary.noBet && <p className="text-xs text-[#FFD166] mt-1">Internal WDE no_bet (owner)</p>}

          {summary.wdeReasons?.length > 0 && (

            <p className="text-[10px] text-[#64748B] mt-1">WDE: {summary.wdeReasons.join(", ")}</p>

          )}

        </div>

        {summary.betQualityScore != null && (

          <div className={`rounded-xl border p-4 ${qualityColorClass(summary.betQualityColor)}`}>

            <p className="text-[10px] uppercase mb-1 flex items-center gap-1"><Shield className="w-3.5 h-3.5" /> Bet Quality</p>

            <p className="text-2xl font-bold">{summary.betQualityScore}</p>

            <p className="text-xs mt-1">{summary.betQualityTier}</p>

          </div>

        )}

        <Card icon={Percent} label="Confidence" value={summary.confidence != null ? `${summary.confidence}%` : "—"} />

        <Card icon={Percent} label="Probability" value={summary.probability != null ? `${summary.probability}%` : "—"} />

        <Card icon={TrendingUp} label="Value Rating" value={summary.valueRating} accent="text-[#7DD3FC]" />

        <Card icon={AlertTriangle} label="Risk" value={String(summary.risk || "").toUpperCase()} accent="text-[#FFD166]" />

        <Card icon={DollarSign} label="Expected Odds" value={summary.expectedOdds} />

        <Card icon={Users} label="Model Agreement" value={summary.modelAgreement != null ? `${summary.modelAgreement}%` : "—"} />

      </div>

      <p className="text-[10px] text-[#64748B] italic">Research only — not betting advice. Bet Quality ≠ prediction probability.</p>

    </section>

  );

}

