import React, { useCallback, useEffect, useState } from "react";
import { Beaker, AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchOwnerResearchLab } from "@/api/saasApi";
import { classifyApiError } from "@/lib/apiError";
import { formatPercent, formatGoalTimingRange } from "@/lib/formatPercent";
import { IntelligenceCard, LoadingSkeleton, ErrorState } from "@/components/intelligence";

function MetricCard({ label, value, sub }) {
  return (
    <div className="rounded-lg bg-white/5 p-3">
      <p className="text-[10px] uppercase text-[#94A3B8]">{label}</p>
      <p className="text-lg font-semibold text-[#F8FAFC]">{value ?? "—"}</p>
      {sub && <p className="text-[10px] text-[#64748B] mt-1">{sub}</p>}
    </div>
  );
}

export default function OwnerResearchLab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchOwnerResearchLab({ refresh }));
    } catch (err) {
      setError(classifyApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(false);
  }, [load]);

  if (loading && !data) return <LoadingSkeleton lines={6} />;
  if (error && !data) return <ErrorState message={error} onRetry={() => load(false)} />;

  const value = data?.value_intelligence || {};
  const valueCards = data?.value_cards || [];
  const timingUi = data?.first_goal_timing_ui || {};
  const evBuckets = data?.ev_bucket_summary || {};
  const evAudit = data?.ev_pipeline_audit || {};
  const edgeSummary = data?.model_vs_market_edge || {};
  const bettingAudit = data?.betting_audit || {};
  const oddsCards = data?.odds_cards || [];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-[#FFD166] flex items-center gap-2">
            <Beaker className="w-6 h-6" /> Research Lab
          </h1>
          <p className="text-sm text-[#94A3B8] mt-1">{data?.disclaimer}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => load(true)} disabled={loading}>
          <RefreshCw className="w-4 h-4 mr-2" /> Refresh value intel
        </Button>
      </div>

      <IntelligenceCard className="border-[#FFD166]/20">
        <p className="text-sm text-[#FFD166] flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> Research only — not betting advice.
        </p>
      </IntelligenceCard>

      <IntelligenceCard>
        <h2 className="font-semibold mb-3 text-[#F8FAFC]">Value bucket summary</h2>
        <p className="text-xs text-[#94A3B8] mb-3">Sample: {value.sample_size ?? 0} matches with odds</p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
          {valueCards.length > 0 ? (
            valueCards.map((card) => (
              <MetricCard key={card.key} label={card.label} value={card.value} sub={card.sub} />
            ))
          ) : (
            <p className="text-sm text-[#94A3B8] col-span-full">No value bucket data yet.</p>
          )}
        </div>
      </IntelligenceCard>

      <IntelligenceCard>
        <h2 className="font-semibold mb-3 text-[#F8FAFC]">EV pipeline</h2>
        {evAudit.detail && (
          <p className="text-xs text-[#FFD166] mb-3">
            Root cause: <span className="text-[#F8FAFC]">{evAudit.root_cause}</span> — {evAudit.detail}
          </p>
        )}
        {Object.keys(evBuckets).length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
            {Object.entries(evBuckets).map(([k, v]) => (
              <MetricCard key={k} label={k.replace(/_/g, " ")} value={v} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-[#94A3B8]">No EV bucket data yet.</p>
        )}
      </IntelligenceCard>

      <IntelligenceCard>
        <h2 className="font-semibold mb-3 text-[#F8FAFC]">Model vs market edge</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <MetricCard label="Analyzed" value={edgeSummary.total_analyzed ?? 0} />
          <MetricCard label="Value" value={edgeSummary.value_candidates ?? 0} />
          <MetricCard label="Watch" value={edgeSummary.watch_only ?? 0} />
          <MetricCard label="No bet" value={edgeSummary.no_bet ?? 0} />
        </div>
        {bettingAudit.detail && (
          <p className="text-xs text-[#94A3B8] mt-3 border-t border-white/5 pt-3">{bettingAudit.detail}</p>
        )}
      </IntelligenceCard>

      <IntelligenceCard>
        <h2 className="font-semibold mb-3 text-[#F8FAFC]">Odds bucket statistics</h2>
        {oddsCards.length > 0 ? (
          <div className="grid sm:grid-cols-2 gap-3">
            {oddsCards.map((row) => (
              <MetricCard
                key={row.label}
                label={row.label}
                value={`${row.matches ?? 0} matches`}
                sub={[
                  row.favorite_win_pct != null ? `Fav win ${formatPercent(row.favorite_win_pct)}` : null,
                  row.over_25_pct != null ? `O2.5 ${formatPercent(row.over_25_pct)}` : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              />
            ))}
          </div>
        ) : (
          <p className="text-sm text-[#94A3B8]">Insufficient odds bucket coverage.</p>
        )}
      </IntelligenceCard>

      <IntelligenceCard>
        <h2 className="font-semibold mb-3 text-[#F8FAFC]">First goal timing</h2>
        <p className="text-xs text-[#94A3B8] mb-3">Status: {timingUi.label || formatGoalTimingRange(null)}</p>
        {(timingUi.cards || []).length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
            {timingUi.cards.map((card) => (
              <MetricCard key={card.id} label={card.title} value={card.value} sub={card.sample ? `n=${card.sample}` : null} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-[#94A3B8]">Run Phase 60B backfill to populate timing artifacts.</p>
        )}
        {(timingUi.ranges || []).length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {timingUi.ranges.map((r) => (
              <div key={r.bucket} className="rounded bg-white/5 px-2 py-1.5">
                <span className="text-[#94A3B8]">{formatGoalTimingRange(r.bucket)}</span>
                <span className="text-[#F8FAFC] ml-2">{r.pct}</span>
              </div>
            ))}
          </div>
        )}
      </IntelligenceCard>

      {(data?.warnings || []).length > 0 && (
        <IntelligenceCard>
          <h2 className="font-semibold mb-2 text-[#F8FAFC]">Data quality warnings</h2>
          <ul className="text-sm text-[#94A3B8] list-disc pl-5 space-y-1">
            {data.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </IntelligenceCard>
      )}
    </div>
  );
}
