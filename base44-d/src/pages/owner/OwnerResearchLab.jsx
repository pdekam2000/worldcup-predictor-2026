import React, { useCallback, useEffect, useState } from "react";
import { Beaker, AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchOwnerResearchLab } from "@/api/saasApi";
import { classifyApiError } from "@/lib/apiError";
import { IntelligenceCard, LoadingSkeleton, ErrorState } from "@/components/intelligence";

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
  const odds = data?.odds_buckets?.favorite_bucket_stats || data?.odds_buckets || {};
  const timing = data?.first_goal_timing;
  const evBuckets = data?.ev_bucket_summary || data?.betting_intelligence?.summary?.ev_buckets;
  const edgeSummary = data?.model_vs_market_edge || data?.betting_intelligence?.summary;

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
        <h2 className="font-semibold mb-3">Value bucket summary</h2>
        <p className="text-xs text-[#94A3B8] mb-3">Sample: {value.sample_size ?? 0} matches with odds</p>
        {value.overall && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm mb-4">
            {Object.entries(value.overall).map(([k, v]) => (
              <div key={k} className="rounded-lg bg-white/5 p-3">
                <p className="text-[10px] uppercase text-[#94A3B8]">{k.replace(/_/g, " ")}</p>
                <p className="text-lg font-semibold">{v != null ? `${v}%` : "—"}</p>
              </div>
            ))}
          </div>
        )}
        <pre className="text-xs overflow-auto max-h-48 text-[#94A3B8]">
          {JSON.stringify(value.favorite_buckets?.slice(0, 5) || [], null, 2)}
        </pre>
      </IntelligenceCard>

      <IntelligenceCard>
        <h2 className="font-semibold mb-3">EV bucket summary</h2>
        {evBuckets ? (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
            {Object.entries(evBuckets).map(([k, v]) => (
              <div key={k} className="rounded-lg bg-white/5 p-3">
                <p className="text-[10px] uppercase text-[#94A3B8]">{k.replace(/_/g, " ")}</p>
                <p className="text-lg font-semibold">{v}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-[#94A3B8]">No EV bucket data yet.</p>
        )}
      </IntelligenceCard>

      <IntelligenceCard>
        <h2 className="font-semibold mb-3">Model vs market edge</h2>
        {edgeSummary ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div className="rounded-lg bg-white/5 p-3"><p className="text-xs text-[#94A3B8]">Analyzed</p><p className="text-lg font-semibold">{edgeSummary.total_analyzed ?? 0}</p></div>
            <div className="rounded-lg bg-white/5 p-3"><p className="text-xs text-[#94A3B8]">Value</p><p className="text-lg font-semibold text-[#00E676]">{edgeSummary.value_candidates ?? 0}</p></div>
            <div className="rounded-lg bg-white/5 p-3"><p className="text-xs text-[#94A3B8]">Watch</p><p className="text-lg font-semibold">{edgeSummary.watch_only ?? 0}</p></div>
            <div className="rounded-lg bg-white/5 p-3"><p className="text-xs text-[#94A3B8]">No bet</p><p className="text-lg font-semibold">{edgeSummary.no_bet ?? 0}</p></div>
          </div>
        ) : (
          <p className="text-sm text-[#94A3B8]">Insufficient snapshot + odds coverage.</p>
        )}
      </IntelligenceCard>

      <IntelligenceCard>
        <h2 className="font-semibold mb-3">Odds bucket statistics</h2>
        <pre className="text-xs overflow-auto max-h-48 text-[#94A3B8]">
          {JSON.stringify(Object.keys(odds).slice(0, 6).reduce((a, k) => ({ ...a, [k]: odds[k] }), {}), null, 2)}
        </pre>
      </IntelligenceCard>

      <IntelligenceCard>
        <h2 className="font-semibold mb-3">First goal timing</h2>
        {timing ? (
          <pre className="text-xs overflow-auto max-h-48 text-[#94A3B8]">{JSON.stringify(timing, null, 2)}</pre>
        ) : (
          <p className="text-sm text-[#94A3B8]">Run Phase 60B backfill to populate timing artifacts.</p>
        )}
      </IntelligenceCard>

      {(data?.warnings || []).length > 0 && (
        <IntelligenceCard>
          <h2 className="font-semibold mb-2">Data quality warnings</h2>
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
