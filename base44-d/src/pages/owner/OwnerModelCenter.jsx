import React, { useCallback, useEffect, useState } from "react";
import { Layers, Shield, FlaskConical } from "lucide-react";
import { fetchOwnerModelCenter } from "@/api/saasApi";
import { classifyApiError } from "@/lib/apiError";
import { IntelligenceCard, LoadingSkeleton, ErrorState } from "@/components/intelligence";

function CertBadge({ level }) {
  const colors = {
    PRODUCTION_READY: "text-[#00E676] border-[#00E676]/30 bg-[#00E676]/10",
    PAPER_READY: "text-[#FFD166] border-[#FFD166]/30 bg-[#FFD166]/10",
    RESEARCH_ONLY: "text-[#94A3B8] border-white/10 bg-white/5",
    BLOCKED: "text-red-300 border-red-500/30 bg-red-500/10",
  };
  const cls = colors[level] || colors.BLOCKED;
  return <span className={`text-xs px-2 py-0.5 rounded-full border ${cls}`}>{level || "BLOCKED"}</span>;
}

function MarketTable({ rows }) {
  if (!rows?.length) {
    return <p className="text-sm text-[#94A3B8]">No market metrics yet.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left">
        <thead className="text-[#94A3B8] text-xs uppercase">
          <tr>
            <th className="py-2 pr-3">Market</th>
            <th className="py-2 pr-3">Preds</th>
            <th className="py-2 pr-3">Eval</th>
            <th className="py-2 pr-3">Pending</th>
            <th className="py-2 pr-3">Winrate</th>
            <th className="py-2 pr-3">Cert</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.market} className="border-t border-white/5">
              <td className="py-2 pr-3 font-medium">{row.market}</td>
              <td className="py-2 pr-3">{row.predictions ?? 0}</td>
              <td className="py-2 pr-3">{row.evaluated ?? 0}</td>
              <td className="py-2 pr-3">{row.pending ?? 0}</td>
              <td className="py-2 pr-3">
                {row.winrate != null ? `${(row.winrate * 100).toFixed(1)}%` : "—"}
              </td>
              <td className="py-2 pr-3">
                <CertBadge level={row.certification} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function OwnerModelCenter() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchOwnerModelCenter());
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

  const prod = data?.production_engine || {};
  const elite = data?.elite_engine || {};
  const rec = data?.recommendations || {};

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#FFD166] flex items-center gap-2">
          <Layers className="w-6 h-6" /> Model Center
        </h1>
        <p className="text-sm text-[#94A3B8] mt-1">Which engine predicts which market — certification at a glance.</p>
      </div>

      <IntelligenceCard glow>
        <div className="flex items-center gap-2 mb-3">
          <Shield className="w-5 h-5 text-[#00E676]" />
          <h2 className="font-semibold text-[#F8FAFC]">Production Engine</h2>
          <span className="text-xs text-[#00E676] ml-auto">{prod.status}</span>
        </div>
        <p className="text-xs text-[#94A3B8] mb-3">Active for public predictions. WDE unchanged.</p>
        <MarketTable rows={prod.market_rows} />
      </IntelligenceCard>

      <IntelligenceCard>
        <div className="flex items-center gap-2 mb-3">
          <FlaskConical className="w-5 h-5 text-[#FFD166]" />
          <h2 className="font-semibold text-[#F8FAFC]">Elite Engine</h2>
          <span className="text-xs text-[#FFD166] ml-auto">{elite.status}</span>
        </div>
        <p className="text-xs text-[#94A3B8] mb-3">Experimental shadow — not promoted to production.</p>
        <MarketTable rows={elite.market_rows} />
      </IntelligenceCard>

      <IntelligenceCard>
        <h2 className="font-semibold text-[#F8FAFC] mb-3">Recommendations</h2>
        <div className="grid md:grid-cols-3 gap-4 text-sm">
          <div>
            <p className="text-xs uppercase text-[#00E676] mb-2">Trusted (production ready)</p>
            <ul className="space-y-1 text-[#94A3B8]">
              {(rec.trusted_markets || []).slice(0, 8).map((m) => (
                <li key={m}>{m}</li>
              ))}
              {!rec.trusted_markets?.length && <li>None yet — need more evaluated results</li>}
            </ul>
          </div>
          <div>
            <p className="text-xs uppercase text-[#FFD166] mb-2">Needs more data</p>
            <ul className="space-y-1 text-[#94A3B8]">
              {(rec.needs_more_results || []).slice(0, 8).map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-xs uppercase text-red-300 mb-2">Paper / no-bet</p>
            <ul className="space-y-1 text-[#94A3B8]">
              {(rec.no_bet_or_paper_only || []).slice(0, 8).map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </div>
        </div>
      </IntelligenceCard>
    </div>
  );
}
