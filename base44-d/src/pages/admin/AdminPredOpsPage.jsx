import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, Play, Layers, Database, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  fetchPredOpsCoverageAdmin,
  fetchPredOpsQueue,
  fetchPredOpsComboReadiness,
  runPredOpsOnce,
} from "@/api/saasApi";

export default function AdminPredOpsPage() {
  const [coverage, setCoverage] = useState(null);
  const [queue, setQueue] = useState(null);
  const [combo, setCombo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [cov, q, c] = await Promise.all([
        fetchPredOpsCoverageAdmin(),
        fetchPredOpsQueue(),
        fetchPredOpsComboReadiness(),
      ]);
      setCoverage(cov);
      setQueue(q);
      setCombo(c);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load PredOps data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runOnce = async (dryRun = false) => {
    setRunning(true);
    setError(null);
    try {
      const res = await runPredOpsOnce({ dryRun, maxJobs: 8 });
      setCoverage(res.coverage || res);
      setCombo(res.combo_readiness || combo);
      if (res.queue) setQueue({ stats: res.queue, jobs: queue?.jobs });
      else await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "PredOps run failed");
    } finally {
      setRunning(false);
    }
  };

  const totals = coverage?.totals || {};
  const model = coverage?.model_coverage || {};
  const egie = coverage?.egie_coverage || {};
  const sched = queue?.last_run?.report?.scheduler || {};

  return (
    <div className="space-y-6 max-w-6xl p-4 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-display font-bold flex items-center gap-2">
            <Layers className="w-7 h-7 text-primary" /> PredOps Core
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Autonomous prediction operations — coverage, queue, snapshots, combo readiness.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={() => runOnce(true)} disabled={running}>
            Dry run
          </Button>
          <Button size="sm" onClick={() => runOnce(false)} disabled={running}>
            <Play className={`w-4 h-4 mr-1 ${running ? "animate-pulse" : ""}`} /> Run (max 8)
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-2 border-primary/20 border-t-primary rounded-full animate-spin" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              ["Fixtures", totals.fixtures ?? 0],
              ["Snapshots", totals.latest_snapshots ?? 0],
              ["Coverage", `${totals.coverage_pct ?? 0}%`],
              ["Fresh", `${totals.completed ?? 0}`],
            ].map(([label, value]) => (
              <div key={label} className="glass rounded-xl p-4">
                <div className="text-xs text-muted-foreground">{label}</div>
                <div className="text-2xl font-bold tabular-nums">{value}</div>
              </div>
            ))}
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <div className="glass rounded-xl p-4">
              <h2 className="font-semibold mb-3 flex items-center gap-2">
                <Database className="w-4 h-4" /> Queue
              </h2>
              <dl className="grid grid-cols-2 gap-2 text-sm">
                {Object.entries(queue?.stats || {}).map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-muted-foreground capitalize">{k}</dt>
                    <dd className="font-bold tabular-nums">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="glass rounded-xl p-4">
              <h2 className="font-semibold mb-3 flex items-center gap-2">
                <Activity className="w-4 h-4" /> Scheduler
              </h2>
              <dl className="text-sm space-y-1">
                <div><span className="text-muted-foreground">Last run:</span> {sched.last_run || queue?.last_run?.started_at || "—"}</div>
                <div><span className="text-muted-foreground">Next est.:</span> {sched.next_run_estimate || "—"}</div>
                <div><span className="text-muted-foreground">Avg gen:</span> {sched.avg_generation_ms ?? "—"} ms</div>
              </dl>
            </div>
          </div>

          <div className="grid md:grid-cols-3 gap-4">
            <div className="glass rounded-xl p-4">
              <h2 className="font-semibold mb-2">Model coverage</h2>
              <dl className="text-sm space-y-1">
                <div>Tier A markets: <strong>{model.tier_a_markets ?? 0}</strong></div>
                <div>Tier B markets: <strong>{model.tier_b_markets ?? 0}</strong></div>
                <div>Agreement: <strong>{model.agreement_pct ?? 0}%</strong></div>
                <div>Disagreement: <strong>{model.disagreement_pct ?? 0}%</strong></div>
              </dl>
            </div>
            <div className="glass rounded-xl p-4">
              <h2 className="font-semibold mb-2">EGIE coverage</h2>
              <dl className="text-sm space-y-1">
                <div>Available: <strong className="text-green-400">{egie.available ?? 0}</strong></div>
                <div>No pick: <strong className="text-yellow-300">{egie.no_pick ?? 0}</strong></div>
                <div>Missing: <strong>{egie.missing ?? 0}</strong></div>
              </dl>
            </div>
            <div className="glass rounded-xl p-4">
              <h2 className="font-semibold mb-2">Combo readiness</h2>
              <dl className="text-sm space-y-1">
                <div>Eligible legs: <strong>{combo?.eligible_legs ?? 0}</strong></div>
                <div>Safe: <strong>{combo?.combos?.safe_ready ? "Yes" : "No"}</strong></div>
                <div>Balanced: <strong>{combo?.combos?.balanced_ready ? "Yes" : "No"}</strong></div>
                <div>High odds: <strong>{combo?.combos?.high_odds_ready ? "Yes" : "No"}</strong></div>
                {combo?.no_combo_reason && (
                  <div className="text-muted-foreground text-xs mt-2">Reason: {combo.no_combo_reason}</div>
                )}
              </dl>
            </div>
          </div>

          <div className="glass rounded-xl p-4 overflow-x-auto">
            <h2 className="font-semibold mb-3">Coverage by competition</h2>
            <table className="w-full text-sm min-w-[720px]">
              <thead>
                <tr className="text-left text-muted-foreground text-xs border-b border-white/10">
                  <th className="pb-2">Competition</th>
                  <th className="pb-2">Fixtures</th>
                  <th className="pb-2">Snapshots</th>
                  <th className="pb-2">Coverage</th>
                  <th className="pb-2">Missing</th>
                  <th className="pb-2">Stale</th>
                  <th className="pb-2">Queued</th>
                  <th className="pb-2">No bet</th>
                </tr>
              </thead>
              <tbody>
                {(coverage?.competitions || []).map((row) => (
                  <tr key={row.competition_key} className="border-b border-white/5">
                    <td className="py-2 font-medium">{row.competition_key}</td>
                    <td className="py-2 tabular-nums">{row.fixtures}</td>
                    <td className="py-2 tabular-nums">{row.latest_snapshots}</td>
                    <td className="py-2 tabular-nums">{row.coverage_pct}%</td>
                    <td className="py-2 tabular-nums text-red-300">{row.missing}</td>
                    <td className="py-2 tabular-nums text-yellow-300">{row.stale}</td>
                    <td className="py-2 tabular-nums">{row.queued}</td>
                    <td className="py-2 tabular-nums">{row.no_bet}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
