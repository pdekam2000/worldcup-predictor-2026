import React, { useCallback, useEffect, useState } from "react";
import { Award, BarChart3, RefreshCw, Shield, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchAdminPerformanceCertification } from "@/api/saasApi";
import { classifyApiError } from "@/lib/apiError";

const LEVEL_STYLES = {
  PRODUCTION_READY: "border-green-500/40 bg-green-500/10 text-green-300",
  PAPER_READY: "border-blue-500/40 bg-blue-500/10 text-blue-300",
  RESEARCH_ONLY: "border-yellow-500/40 bg-yellow-500/10 text-yellow-300",
  BLOCKED: "border-slate-500/40 bg-slate-500/10 text-slate-300",
};

function Panel({ children, className = "" }) {
  return (
    <div className={`rounded-xl border border-white/10 bg-card/50 p-4 sm:p-5 ${className}`}>
      {children}
    </div>
  );
}

function Badge({ level }) {
  const style = LEVEL_STYLES[level] || LEVEL_STYLES.BLOCKED;
  return <span className={`text-xs px-2 py-1 rounded border ${style}`}>{level || "BLOCKED"}</span>;
}

function pct(v) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

export default function AdminPerformancePage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchAdminPerformanceCertification();
      setData(result);
    } catch (err) {
      setError(classifyApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const overall = data?.overall || {};
  const engines = data?.engines || {};
  const rolling = data?.rolling || {};

  return (
    <div className="max-w-6xl mx-auto space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Award className="w-6 h-6 text-primary" />
            Elite Performance Center
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Autonomous certification metrics. Elite remains experimental until certified by results.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <Panel className="border-red-500/30 text-red-200">{error}</Panel>
      )}

      {loading && !data && (
        <Panel className="text-center text-muted-foreground">Loading performance certification…</Panel>
      )}

      {data && (
        <>
          <div className="grid sm:grid-cols-2 gap-4">
            <Panel>
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-semibold flex items-center gap-2">
                  <Shield className="w-4 h-4" /> Production
                </h2>
                <Badge level={overall.production_certification} />
              </div>
              <p className="text-sm text-muted-foreground">Evaluated: {engines.production?.evaluated ?? 0}</p>
              <p className="text-2xl font-bold mt-1">{pct(engines.production?.winrate)}</p>
            </Panel>
            <Panel>
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-semibold flex items-center gap-2">
                  <TrendingUp className="w-4 h-4" /> Elite Shadow
                </h2>
                <Badge level={overall.elite_certification} />
              </div>
              <p className="text-sm text-muted-foreground">Evaluated: {engines.elite_shadow?.evaluated ?? 0}</p>
              <p className="text-2xl font-bold mt-1">{pct(engines.elite_shadow?.winrate)}</p>
            </Panel>
          </div>

          <Panel>
            <h2 className="font-semibold mb-3 flex items-center gap-2">
              <BarChart3 className="w-4 h-4" /> Rolling performance
            </h2>
            <div className="grid sm:grid-cols-3 gap-3 text-sm">
              {Object.entries(rolling).map(([window, stats]) => (
                <div key={window} className="rounded-lg border border-white/10 p-3">
                  <p className="text-muted-foreground mb-1">{window}</p>
                  <p>Prod: {pct(stats.production?.winrate)} ({stats.production?.evaluated ?? 0})</p>
                  <p>Elite: {pct(stats.elite_shadow?.winrate)} ({stats.elite_shadow?.evaluated ?? 0})</p>
                </div>
              ))}
            </div>
          </Panel>

          <Panel>
            <h2 className="font-semibold mb-3">Latest evaluated</h2>
            {(data.latest_evaluated || []).length === 0 ? (
              <p className="text-sm text-muted-foreground">No evaluated snapshots yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-muted-foreground border-b border-white/10">
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
          </Panel>

          <p className="text-xs text-muted-foreground">
            Research statistics and experimental predictions. Not betting advice.
          </p>
        </>
      )}
    </div>
  );
}
