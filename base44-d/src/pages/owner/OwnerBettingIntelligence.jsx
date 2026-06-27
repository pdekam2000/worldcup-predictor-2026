import React, { useCallback, useEffect, useState } from "react";
import { DollarSign, AlertTriangle } from "lucide-react";
import { fetchOwnerBettingIntelligence } from "@/api/saasApi";
import { classifyApiError } from "@/lib/apiError";
import { formatPercent } from "@/lib/formatPercent";
import { IntelligenceCard, LoadingSkeleton, ErrorState } from "@/components/intelligence";

function BetTable({ rows, empty }) {
  if (!rows?.length) {
    return <p className="text-sm text-[#94A3B8]">{empty}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left">
        <thead className="text-[#94A3B8] text-xs uppercase">
          <tr>
            <th className="py-2 pr-2">Fixture</th>
            <th className="py-2 pr-2">Market</th>
            <th className="py-2 pr-2">Model</th>
            <th className="py-2 pr-2">Odds</th>
            <th className="py-2 pr-2">Edge</th>
            <th className="py-2 pr-2">EV</th>
            <th className="py-2 pr-2">Kelly 0.25</th>
            <th className="py-2 pr-2">Tier</th>
            <th className="py-2 pr-2">Label</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.snapshot_id}-${r.market_id}`} className="border-t border-white/5">
              <td className="py-2 pr-2 max-w-[140px] truncate">{r.fixture}</td>
              <td className="py-2 pr-2">{r.market_id}</td>
              <td className="py-2 pr-2">{formatPercent(r.model_probability)}</td>
              <td className="py-2 pr-2">{formatPercent(r.implied_probability)}</td>
              <td className="py-2 pr-2">{formatPercent(r.edge)}</td>
              <td className="py-2 pr-2">{r.ev != null ? r.ev.toFixed(3) : "—"}</td>
              <td className="py-2 pr-2">{r.kelly_capped != null ? formatPercent(r.kelly_capped) : "—"}</td>
              <td className="py-2 pr-2">{r.confidence_tier || "—"}</td>
              <td className="py-2 pr-2 text-xs">{r.label}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function OwnerBettingIntelligence() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchOwnerBettingIntelligence());
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

  const summary = data?.summary || {};
  const audit = data?.audit || {};

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#FFD166] flex items-center gap-2">
          <DollarSign className="w-6 h-6" /> Betting Intelligence
        </h1>
        <p className="text-sm text-[#94A3B8] mt-1">{data?.disclaimer}</p>
      </div>

      <IntelligenceCard className="border-[#FFD166]/20">
        <p className="text-sm text-[#FFD166] flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> Research only — not betting advice.
        </p>
      </IntelligenceCard>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
        <IntelligenceCard><p className="text-[#94A3B8] text-xs">Analyzed</p><p className="text-xl font-bold">{summary.total_analyzed ?? 0}</p></IntelligenceCard>
        <IntelligenceCard><p className="text-[#94A3B8] text-xs">Value candidates</p><p className="text-xl font-bold text-[#00E676]">{summary.value_candidates ?? 0}</p></IntelligenceCard>
        <IntelligenceCard><p className="text-[#94A3B8] text-xs">Watch only</p><p className="text-xl font-bold">{summary.watch_only ?? 0}</p></IntelligenceCard>
        <IntelligenceCard><p className="text-[#94A3B8] text-xs">No odds</p><p className="text-xl font-bold text-[#FFD166]">{summary.no_odds_available ?? 0}</p></IntelligenceCard>
        <IntelligenceCard>
          <p className="text-[#94A3B8] text-xs">Bookmakers (avg)</p>
          <p className="text-xl font-bold">{summary.available_bookmakers_avg ?? 0}</p>
        </IntelligenceCard>
      </div>

      {audit.detail && (
        <IntelligenceCard className="border-[#FFD166]/20">
          <p className="text-xs text-[#94A3B8]">
            Audit: <span className="text-[#FFD166]">{audit.root_cause}</span> — {audit.detail}
          </p>
        </IntelligenceCard>
      )}

      <IntelligenceCard>
        <h2 className="font-semibold mb-3">Value candidates</h2>
        <BetTable rows={data?.value_candidates} empty="No value candidates with current data." />
      </IntelligenceCard>

      <IntelligenceCard>
        <h2 className="font-semibold mb-3">No-bet / blocked</h2>
        <BetTable rows={data?.no_bet} empty="No blocked rows." />
      </IntelligenceCard>
    </div>
  );
}
