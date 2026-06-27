import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, Play, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchOwnerPrefetchCoverage, runOwnerPrefetchOnce } from "@/api/saasApi";

export default function OwnerPrefetchCoveragePage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchOwnerPrefetchCoverage();
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load coverage");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runOnce = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await runOwnerPrefetchOnce();
      setData(res.coverage || res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Prefetch run failed");
    } finally {
      setRunning(false);
    }
  };

  const totals = data?.totals || {};
  const combo = data?.combo_readiness || {};

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-display font-bold flex items-center gap-2">
            <Database className="w-7 h-7 text-primary" /> Prediction Prefetch Coverage
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Background cache coverage for Match Center and Combo Tips (orchestration only).
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
          <Button size="sm" onClick={runOnce} disabled={running}>
            <Play className={`w-4 h-4 mr-1 ${running ? "animate-pulse" : ""}`} /> Run prefetch
          </Button>
        </div>
      </div>

      {error && <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-primary/20 border-t-primary rounded-full animate-spin" /></div>
      ) : data ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              ["Fixtures", totals.fixtures ?? 0],
              ["Predictions", totals.predictions ?? 0],
              ["Coverage", `${totals.coverage_pct ?? 0}%`],
              ["Bettable", `${totals.bettable_pct ?? 0}%`],
            ].map(([label, value]) => (
              <div key={label} className="glass rounded-xl p-4">
                <div className="text-xs text-muted-foreground">{label}</div>
                <div className="text-2xl font-bold tabular-nums">{value}</div>
              </div>
            ))}
          </div>

          <div className="grid md:grid-cols-3 gap-4">
            {[
              ["Fresh", totals.fresh ?? 0, "text-green-400"],
              ["Stale", totals.stale ?? 0, "text-yellow-300"],
              ["Missing", totals.missing ?? 0, "text-red-300"],
            ].map(([label, value, color]) => (
              <div key={label} className="glass rounded-xl p-4">
                <div className="text-xs text-muted-foreground">{label}</div>
                <div className={`text-xl font-bold tabular-nums ${color}`}>{value}</div>
              </div>
            ))}
          </div>

          <div className="glass rounded-xl p-4">
            <h2 className="font-semibold mb-2">Combo readiness</h2>
            <dl className="grid sm:grid-cols-3 gap-3 text-sm">
              <div><dt className="text-muted-foreground">Ready</dt><dd className="text-green-400 font-bold">{combo.ready ?? 0}</dd></div>
              <div><dt className="text-muted-foreground">Waiting</dt><dd>{combo.waiting_for_prediction ?? 0}</dd></div>
              <div><dt className="text-muted-foreground">No bet</dt><dd className="text-yellow-300">{combo.no_bet ?? 0}</dd></div>
            </dl>
          </div>

          <div className="glass rounded-xl p-4 overflow-x-auto">
            <h2 className="font-semibold mb-3">By competition</h2>
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="text-left text-muted-foreground text-xs border-b border-white/10">
                  <th className="pb-2">Competition</th>
                  <th className="pb-2">Status</th>
                  <th className="pb-2">Fixtures</th>
                  <th className="pb-2">Predictions</th>
                  <th className="pb-2">Bettable</th>
                  <th className="pb-2">Coverage</th>
                  <th className="pb-2">Fresh</th>
                  <th className="pb-2">Stale</th>
                  <th className="pb-2">Missing</th>
                </tr>
              </thead>
              <tbody>
                {(data.competitions || []).map((row) => (
                  <tr key={row.competition_key} className="border-b border-white/5">
                    <td className="py-2 font-medium">{row.competition_key}</td>
                    <td className="py-2 tabular-nums text-xs">
                      {row.season_status === "OFF_SEASON" ? (
                        <span className="text-[#FFD166]">OFF_SEASON</span>
                      ) : (
                        row.season_status || "IN_SEASON"
                      )}
                    </td>
                    <td className="py-2 tabular-nums">{row.season_status === "OFF_SEASON" ? "—" : row.fixtures}</td>
                    <td className="py-2 tabular-nums">{row.predictions}</td>
                    <td className="py-2 tabular-nums">{row.bettable}</td>
                    <td className="py-2 tabular-nums">{row.season_status === "OFF_SEASON" ? "—" : `${row.coverage_pct}%`}</td>
                    <td className="py-2 tabular-nums text-green-400">{row.fresh}</td>
                    <td className="py-2 tabular-nums text-yellow-300">{row.stale}</td>
                    <td className="py-2 tabular-nums text-red-300">{row.missing}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}
