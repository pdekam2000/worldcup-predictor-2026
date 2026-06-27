import React, { useCallback, useEffect, useState } from "react";
import { Award, BarChart3, RefreshCw, Shield, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchOwnerPerformanceCenter } from "@/api/saasApi";
import { classifyApiError } from "@/lib/apiError";
import { formatPercent } from "@/lib/formatPercent";
import { IntelligenceCard, LoadingSkeleton, ErrorState } from "@/components/intelligence";

function pct(v) {
  return formatPercent(v);
}

function EnginePanel({ title, icon: Icon, data, accent }) {
  const evaluated = data?.evaluated ?? 0;
  const correct = data?.correct ?? 0;
  const wrong = data?.wrong ?? 0;
  return (
    <IntelligenceCard glow>
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold flex items-center gap-2 text-[#F8FAFC]">
          <Icon className={`w-4 h-4 ${accent}`} /> {title}
        </h2>
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-xs text-[#94A3B8]">Evaluated</p>
          <p className="text-xl font-bold">{evaluated}</p>
        </div>
        <div>
          <p className="text-xs text-[#94A3B8]">Winrate</p>
          <p className="text-xl font-bold">{pct(data?.winrate)}</p>
        </div>
        <div>
          <p className="text-xs text-[#94A3B8]">Correct</p>
          <p className="text-lg text-[#00E676]">{correct}</p>
        </div>
        <div>
          <p className="text-xs text-[#94A3B8]">Wrong</p>
          <p className="text-lg text-red-300">{wrong}</p>
        </div>
      </div>
    </IntelligenceCard>
  );
}

export default function OwnerPerformancePage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchOwnerPerformanceCenter());
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

  const prod = data?.production || {};
  const elite = data?.elite_shadow || {};
  const rolling = data?.rolling || {};

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-[#FFD166] flex items-center gap-2">
            <Award className="w-6 h-6" /> Performance Center
          </h1>
          <p className="text-sm text-[#94A3B8] mt-1">
            Production + elite metrics bridged from autonomous evals and worldcup_prediction_evaluations.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <EnginePanel title="Production" icon={Shield} data={prod} accent="text-[#00E676]" />
        <EnginePanel title="Elite Shadow" icon={TrendingUp} data={elite} accent="text-[#FFD166]" />
      </div>

      <IntelligenceCard>
        <h2 className="font-semibold mb-3 flex items-center gap-2 text-[#F8FAFC]">
          <BarChart3 className="w-4 h-4" /> Rolling windows (evaluated_at)
        </h2>
        <div className="grid sm:grid-cols-3 gap-3 text-sm">
          {Object.entries(rolling).map(([window, stats]) => {
            const p = stats?.production || {};
            const wc = p?.worldcup || {};
            const e = stats?.elite_shadow || {};
            const prodEval = wc.evaluated || p.evaluated || 0;
            const prodWr = wc.winrate ?? p.winrate;
            return (
              <div key={window} className="rounded-lg border border-white/10 p-3">
                <p className="text-[#94A3B8] mb-1 font-medium">{window}</p>
                <p className="text-[#F8FAFC]">Prod: {pct(prodWr)} ({prodEval})</p>
                <p className="text-[#94A3B8]">Elite: {pct(e.winrate)} ({e.evaluated ?? 0})</p>
              </div>
            );
          })}
        </div>
      </IntelligenceCard>

      <IntelligenceCard>
        <h2 className="font-semibold mb-3 text-[#F8FAFC]">Latest evaluated</h2>
        {(data?.latest_evaluated || []).length === 0 ? (
          <p className="text-sm text-[#94A3B8]">No evaluated snapshots yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[#94A3B8] border-b border-white/10">
                  <th className="py-2 pr-3">Fixture</th>
                  <th className="py-2 pr-3">Engine</th>
                  <th className="py-2 pr-3">Market</th>
                  <th className="py-2">Result</th>
                </tr>
              </thead>
              <tbody>
                {data.latest_evaluated.map((row) => (
                  <tr key={row.id} className="border-b border-white/5">
                    <td className="py-2 pr-3">{row.home_team} vs {row.away_team}</td>
                    <td className="py-2 pr-3">{row.engine}</td>
                    <td className="py-2 pr-3">{row.market_id}</td>
                    <td className="py-2">{row.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </IntelligenceCard>
    </div>
  );
}
