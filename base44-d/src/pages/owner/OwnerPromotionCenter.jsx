import React, { useCallback, useEffect, useState } from "react";
import { TrendingUp, AlertTriangle } from "lucide-react";
import { fetchOwnerPromotionStatus } from "@/api/saasApi";
import { classifyApiError } from "@/lib/apiError";
import { formatPercent } from "@/lib/formatPercent";
import { IntelligenceCard, LoadingSkeleton, ErrorState } from "@/components/intelligence";

const STATE_COLORS = {
  PRODUCTION_READY: "text-[#00E676] border-[#00E676]/30",
  MICRO_TEST_READY: "text-[#7DD3FC] border-[#7DD3FC]/30",
  PAPER_READY: "text-[#FFD166] border-[#FFD166]/30",
  RESEARCH_ONLY: "text-[#94A3B8] border-white/10",
  BLOCKED: "text-red-300 border-red-500/30",
};

const REC_LABELS = {
  keep_production: "Keep production",
  paper_test_elite: "Paper test elite",
  micro_test_elite: "Micro test elite",
  eligible_for_production_review: "Eligible for production review",
};

function EngineMini({ label, metrics }) {
  if (!metrics) return null;
  return (
    <div className="text-xs text-[#94A3B8] space-y-1">
      <p className="font-medium text-white/80">{label}</p>
      <p>Eval: {metrics.evaluated ?? 0} · Win: {formatPercent(metrics.winrate)}</p>
      <p>ROI: {metrics.roi != null ? formatPercent(metrics.roi) : "n/a"} · Cert: {metrics.certification}</p>
    </div>
  );
}

function ProgressBar({ label, current, required }) {
  const pct = required > 0 ? Math.min(100, Math.round((current / required) * 100)) : 0;
  return (
    <div>
      <div className="flex justify-between text-xs text-[#94A3B8] mb-1">
        <span>{label}</span>
        <span className="font-mono text-[#F8FAFC]">{current} / {required}</span>
      </div>
      <div className="h-2 rounded-full bg-white/10 overflow-hidden">
        <div className="h-full bg-[#00E676]/70 rounded-full transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function OwnerPromotionCenter() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchOwnerPromotionStatus());
    } catch (err) {
      setError(classifyApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !data) return <LoadingSkeleton lines={6} />;
  if (error && !data) return <ErrorState message={error} onRetry={load} />;

  const markets = data?.markets || [];
  const summary = data?.summary || {};
  const progress = data?.promotion_progress || {};

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#FFD166] flex items-center gap-2">
          <TrendingUp className="w-6 h-6" /> Promotion Center
        </h1>
        <p className="text-sm text-[#94A3B8] mt-1">{data?.disclaimer}</p>
      </div>

      <IntelligenceCard className="border-[#FFD166]/20">
        <p className="text-sm text-[#FFD166] flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> Recommendations only — public routing unchanged.
        </p>
      </IntelligenceCard>

      <IntelligenceCard>
        <h2 className="font-semibold text-[#F8FAFC] mb-4">Elite promotion gates</h2>
        <div className="space-y-4">
          <ProgressBar label="Paper" current={progress.paper?.current ?? 0} required={progress.paper?.required ?? 100} />
          <ProgressBar label="Micro test" current={progress.micro?.current ?? 0} required={progress.micro?.required ?? 300} />
          <ProgressBar label="Production" current={progress.prod?.current ?? 0} required={progress.prod?.required ?? 1000} />
        </div>
      </IntelligenceCard>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <IntelligenceCard><p className="text-[#94A3B8] text-xs">Blocked</p><p className="text-xl font-bold">{summary.blocked_count ?? 0}</p></IntelligenceCard>
        <IntelligenceCard><p className="text-[#94A3B8] text-xs">Paper ready</p><p className="text-xl font-bold">{summary.paper_ready_count ?? 0}</p></IntelligenceCard>
        <IntelligenceCard><p className="text-[#94A3B8] text-xs">Micro test</p><p className="text-xl font-bold">{summary.micro_test_count ?? 0}</p></IntelligenceCard>
        <IntelligenceCard><p className="text-[#94A3B8] text-xs">Prod review</p><p className="text-xl font-bold">{summary.production_review_count ?? 0}</p></IntelligenceCard>
      </div>

      <div className="space-y-4">
        {markets.map((m) => (
          <IntelligenceCard key={m.market_id}>
            <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
              <h2 className="font-semibold text-lg">{m.market_id}</h2>
              <span className={`text-xs px-2 py-1 rounded border ${STATE_COLORS[m.promotion_state] || STATE_COLORS.BLOCKED}`}>
                {m.promotion_state}
              </span>
            </div>
            <div className="grid md:grid-cols-2 gap-4 mb-3">
              <EngineMini label="Production Engine" metrics={m.production} />
              <EngineMini label="Elite Engine" metrics={m.elite} />
            </div>
            <p className="text-sm mb-2">
              Recommendation: <span className="text-[#FFD166]">{REC_LABELS[m.recommendation] || m.recommendation}</span>
            </p>
            {m.evaluations_remaining && (
              <p className="text-xs text-[#94A3B8] mb-2">
                Remaining evals — paper: {m.evaluations_remaining.paper_ready} · micro: {m.evaluations_remaining.micro_test_ready} · prod: {m.evaluations_remaining.production_ready}
              </p>
            )}
            {(m.blocked_reasons || []).length > 0 && (
              <ul className="text-xs text-red-300 list-disc pl-5">
                {m.blocked_reasons.map((r) => <li key={r}>{r}</li>)}
              </ul>
            )}
            {(m.missing_data || []).length > 0 && (
              <ul className="text-xs text-[#94A3B8] list-disc pl-5 mt-1">
                {m.missing_data.map((r) => <li key={r}>{r}</li>)}
              </ul>
            )}
          </IntelligenceCard>
        ))}
      </div>
    </div>
  );
}
