import React, { useEffect, useState } from "react";
import { FlaskConical, TrendingUp } from "lucide-react";
import { fetchEcseForFixture } from "@/api/worldcupApi";
import { Progress } from "@/components/ui/progress";
import { TRUST_RESEARCH_ONLY } from "@/lib/trustCopy";

function tierClass(tier) {
  if (tier === "A") return "bg-[#00E676]/15 text-[#00E676] border-[#00E676]/30";
  if (tier === "B") return "bg-[#7DD3FC]/15 text-[#7DD3FC] border-[#7DD3FC]/30";
  return "bg-white/5 text-[#94A3B8] border-white/10";
}

function ScoreBar({ scoreline, probabilityPct, rank, maxPct }) {
  const width = maxPct > 0 ? Math.min(100, (probabilityPct / maxPct) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="font-semibold text-[#F8FAFC] tabular-nums">
          #{rank} {scoreline}
        </span>
        <span className="text-[#94A3B8] tabular-nums">{probabilityPct.toFixed(1)}%</span>
      </div>
      <Progress value={width} className="h-2 bg-white/10" />
    </div>
  );
}

function EliteAdjustmentsBlock({ elite }) {
  if (!elite) return null;
  return (
    <div className="rounded-lg border border-[#7DD3FC]/20 bg-[#7DD3FC]/5 p-3 space-y-2">
      <p className="text-[10px] uppercase tracking-wide text-[#7DD3FC]">Elite lambda bridge (shadow)</p>
      <div className="grid grid-cols-2 gap-2 text-xs text-[#94A3B8]">
        <div>
          <p className="text-[#64748B]">Production λ</p>
          <p className="text-[#F8FAFC]">
            {elite.production_lambda_home?.toFixed?.(2) ?? "—"} / {elite.production_lambda_away?.toFixed?.(2) ?? "—"}
          </p>
          <p className="text-[#64748B] mt-1">Scoreline {elite.production_scoreline || "—"}</p>
        </div>
        <div>
          <p className="text-[#64748B]">Shadow λ</p>
          <p className="text-[#F8FAFC]">
            {elite.shadow_lambda_home?.toFixed?.(2) ?? "—"} / {elite.shadow_lambda_away?.toFixed?.(2) ?? "—"}
          </p>
          <p className="text-[#64748B] mt-1">Scoreline {elite.shadow_scoreline || "—"}</p>
        </div>
      </div>
      {elite.data_quality_scale != null && (
        <p className="text-[10px] text-[#64748B]">
          Data quality scale {Math.round(elite.data_quality_scale * 100)}%
          {elite.global_cap_applied ? " · global cap applied" : ""}
        </p>
      )}
    </div>
  );
}

function BestValueBlock({ bestValue, topScoreline }) {
  if (!bestValue) return null;
  const edge = bestValue.value_score;
  const positive = edge > 0;
  return (
    <div
      className={`rounded-lg border p-3 space-y-1 ${
        positive ? "border-[#00E676]/25 bg-[#00E676]/5" : "border-white/10 bg-white/[0.02]"
      }`}
    >
      <div className="flex items-center gap-2">
        <TrendingUp className={`w-4 h-4 ${positive ? "text-[#00E676]" : "text-[#94A3B8]"}`} />
        <p className="text-[10px] uppercase tracking-wide text-[#94A3B8]">Best value — {topScoreline}</p>
      </div>
      <p className="text-sm text-[#F8FAFC]">
        Model {(bestValue.model_probability * 100).toFixed(1)}% vs market {(bestValue.implied_probability * 100).toFixed(1)}%
        {bestValue.market_odds != null && ` @ ${bestValue.market_odds}`}
      </p>
      <p className={`text-xs font-semibold ${positive ? "text-[#00E676]" : "text-[#94A3B8]"}`}>
        Edge {edge > 0 ? "+" : ""}
        {edge.toFixed(2)} pp · EV {(bestValue.expected_value * 100).toFixed(1)}%
      </p>
    </div>
  );
}

export default function EcseExactScorePanel({ fixtureId, compact = false, className = "" }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!fixtureId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchEcseForFixture(fixtureId)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load ECSE");
          setData(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [fixtureId]);

  if (loading) {
    return (
      <div className={`rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 ${className}`}>
        <p className="text-xs text-[#64748B]">Loading ECSE exact scores…</p>
      </div>
    );
  }

  if (error) {
    return null;
  }

  if (!data?.available) {
    if (compact) return null;
    return (
      <div className={`rounded-lg border border-dashed border-white/[0.08] bg-white/[0.02] p-4 ${className}`}>
        <div className="flex items-center gap-2 mb-2">
          <FlaskConical className="w-4 h-4 text-[#64748B]" />
          <p className="text-sm font-medium text-[#94A3B8]">ECSE Exact Score Engine</p>
        </div>
        <p className="text-xs text-[#64748B]">
          {data?.unavailable_reason === "no_registry_mapping"
            ? "No historical registry mapping for this fixture yet."
            : "Score distribution not available for this fixture."}
        </p>
        {data?.elite_adjustments && !compact && (
          <div className="mt-3">
            <EliteAdjustmentsBlock elite={data.elite_adjustments} />
          </div>
        )}
      </div>
    );
  }

  const scores = data.top_scores || [];
  const maxPct = scores.length ? Math.max(...scores.map((s) => s.probability_pct)) : 0;
  const top = scores[0];

  return (
    <div className={`rounded-lg border border-[#A78BFA]/20 bg-[#A78BFA]/5 p-4 space-y-3 ${className}`}>
      <div className="flex flex-wrap items-center gap-2">
        <FlaskConical className="w-4 h-4 text-[#A78BFA]" />
        <p className="text-sm font-semibold text-[#F8FAFC]">ECSE Exact Scores</p>
        {data.confidence_tier && (
          <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${tierClass(data.confidence_tier)}`}>
            Tier {data.confidence_tier}
          </span>
        )}
        {!compact && data.lambda && (
          <span className="text-[10px] text-[#64748B]">
            λ {data.lambda.lambda_home} / {data.lambda.lambda_away}
          </span>
        )}
      </div>

      <div className="space-y-2">
        {scores.map((s) => (
          <ScoreBar
            key={s.scoreline}
            scoreline={s.scoreline}
            probabilityPct={s.probability_pct}
            rank={s.rank}
            maxPct={maxPct}
          />
        ))}
      </div>

      {!compact && <BestValueBlock bestValue={data.best_value} topScoreline={top?.scoreline} />}
      {!compact && <EliteAdjustmentsBlock elite={data.elite_adjustments} />}

      <p className="text-[10px] text-[#475569] italic">{data.disclaimer || TRUST_RESEARCH_ONLY}</p>
    </div>
  );
}
