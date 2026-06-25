import React, { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Target, Filter, RefreshCw, ChevronRight, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  fetchAdminAccuracyEvaluations,
  fetchAdminFixtureInspector,
  rebuildAdminAccuracy,
} from "@/api/saasApi";

const STATUS_COLORS = {
  green: "bg-green-500/15 text-green-400 border-green-500/30",
  red: "bg-red-500/15 text-red-400 border-red-500/30",
  yellow: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  gray: "bg-white/5 text-muted-foreground border-white/10",
};

function StatCard({ label, value, sub }) {
  return (
    <div className="glass rounded-xl p-4">
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      <div className="text-2xl font-display font-bold">{value ?? "—"}</div>
      {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
    </div>
  );
}

function pct(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return `${Math.round(Number(v) * 1000) / 10}%`;
}

export default function AdminAccuracyCenter() {
  const [stats, setStats] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [pickTier, setPickTier] = useState("all");
  const [confidenceMin, setConfidenceMin] = useState("");
  const [confidenceMax, setConfidenceMax] = useState("");
  const [inspector, setInspector] = useState(null);
  const [inspectorLoading, setInspectorLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAdminAccuracyEvaluations({
        status: statusFilter,
        pick_tier: pickTier,
        confidence_min: confidenceMin ? Number(confidenceMin) : undefined,
        confidence_max: confidenceMax ? Number(confidenceMax) : undefined,
        limit: 100,
      });
      setStats(data.statistics);
      setRows(data.rows || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load accuracy data");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, pickTier, confidenceMin, confidenceMax]);

  useEffect(() => {
    load();
  }, [load]);

  const openInspector = async (fixtureId) => {
    setInspectorLoading(true);
    try {
      const detail = await fetchAdminFixtureInspector(fixtureId);
      setInspector(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Inspector failed");
    } finally {
      setInspectorLoading(false);
    }
  };

  const onRebuild = async () => {
    try {
      await rebuildAdminAccuracy({ evaluate: true });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rebuild failed");
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-display font-bold flex items-center gap-2">
            <Target className="w-6 h-6 text-primary" /> Admin Accuracy Center
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Phase 33 background predictions — official vs caution evaluation tracking.
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Test/validation rows are quarantined and excluded from public accuracy.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" className="border-white/10" onClick={onRebuild}>
          <RefreshCw className="w-4 h-4 mr-2" /> Rebuild &amp; Evaluate
        </Button>
      </div>

      {error && <div className="glass rounded-xl p-3 text-sm text-red-300">{error}</div>}

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <StatCard label="Total Predictions" value={stats.total_predictions} />
          <StatCard label="Evaluated" value={stats.evaluated_predictions} />
          <StatCard label="Correct" value={stats.correct} />
          <StatCard label="Wrong" value={stats.wrong} />
          <StatCard label="Overall Winrate" value={pct(stats.overall_winrate)} />
          <StatCard label="Official Winrate" value={pct(stats.official_pick_winrate)} sub="confidence ≥ 60" />
          <StatCard label="Caution Winrate" value={pct(stats.caution_pick_winrate)} sub="below threshold" />
          <StatCard label="Safe Pick" value={pct(stats.safe_pick_winrate)} />
          <StatCard label="Value Pick" value={pct(stats.value_pick_winrate)} />
          <StatCard label="Aggressive" value={pct(stats.aggressive_pick_winrate)} />
          <StatCard label="No-Bet Rate" value={pct(stats.no_bet_rate)} sub="internal flag" />
          <StatCard label="Pending" value={stats.pending} />
        </div>
      )}

      <div className="glass rounded-xl p-4 flex flex-wrap gap-3 items-end">
        <Filter className="w-4 h-4 text-muted-foreground mb-2" />
        <select
          className="bg-background border border-white/10 rounded-lg px-3 py-2 text-sm"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="all">All statuses</option>
          <option value="correct">Correct</option>
          <option value="wrong">Wrong</option>
          <option value="pending">Pending</option>
        </select>
        <select
          className="bg-background border border-white/10 rounded-lg px-3 py-2 text-sm"
          value={pickTier}
          onChange={(e) => setPickTier(e.target.value)}
        >
          <option value="all">All tiers</option>
          <option value="official">Official Picks</option>
          <option value="caution">Caution Picks</option>
        </select>
        <Input
          placeholder="Min confidence"
          className="w-28 bg-background border-white/10"
          value={confidenceMin}
          onChange={(e) => setConfidenceMin(e.target.value)}
        />
        <Input
          placeholder="Max confidence"
          className="w-28 bg-background border-white/10"
          value={confidenceMax}
          onChange={(e) => setConfidenceMax(e.target.value)}
        />
        <Button type="button" size="sm" onClick={load}>Apply</Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
        </div>
      ) : (
        <div className="glass rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-muted-foreground">
                  <th className="p-3">Match</th>
                  <th className="p-3">Kickoff</th>
                  <th className="p-3">Conf.</th>
                  <th className="p-3">Tier</th>
                  <th className="p-3">Safe</th>
                  <th className="p-3">Value</th>
                  <th className="p-3">Aggressive</th>
                  <th className="p-3">Result</th>
                  <th className="p-3">Status</th>
                  <th className="p-3" />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.fixture_id} className="border-b border-white/5 hover:bg-white/[0.02]">
                    <td className="p-3 font-medium">{row.match}</td>
                    <td className="p-3 text-muted-foreground text-xs">{row.kickoff_utc?.slice(0, 16) || "—"}</td>
                    <td className="p-3">{row.confidence != null ? `${Math.round(row.confidence)}%` : "—"}</td>
                    <td className="p-3 capitalize">{row.pick_tier || "—"}</td>
                    <td className="p-3 text-xs">{row.safe_pick || "—"}</td>
                    <td className="p-3 text-xs">{row.value_pick || "—"}</td>
                    <td className="p-3 text-xs">{row.aggressive_pick || "—"}</td>
                    <td className="p-3">{row.final_score || row.actual_result || "—"}</td>
                    <td className="p-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs border ${STATUS_COLORS[row.status_color] || STATUS_COLORS.gray}`}>
                        {row.evaluation_status}
                      </span>
                    </td>
                    <td className="p-3">
                      <button
                        type="button"
                        className="text-primary hover:underline inline-flex items-center gap-1 text-xs"
                        onClick={() => openInspector(row.fixture_id)}
                      >
                        Inspect <ChevronRight className="w-3 h-3" />
                      </button>
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={10} className="p-8 text-center text-muted-foreground">
                      No evaluation rows yet. Run background prediction + evaluate jobs.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(inspector || inspectorLoading) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60" onClick={() => setInspector(null)}>
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            className="glass rounded-2xl max-w-3xl w-full max-h-[85vh] overflow-y-auto p-6 border border-white/10"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between mb-4">
              <h2 className="font-display font-bold text-lg">Match Inspector</h2>
              <button type="button" onClick={() => setInspector(null)}><X className="w-5 h-5" /></button>
            </div>
            {inspectorLoading ? (
              <div className="flex justify-center py-12">
                <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
              </div>
            ) : inspector && (
              <div className="space-y-4 text-sm">
                <div className="grid sm:grid-cols-2 gap-3">
                  <div><span className="text-muted-foreground">Confidence:</span> {inspector.confidence ?? "—"}</div>
                  <div><span className="text-muted-foreground">Data quality:</span> {inspector.data_quality ?? "—"}</div>
                  <div><span className="text-muted-foreground">National form:</span> {inspector.national_form_score ?? "—"}</div>
                  <div><span className="text-muted-foreground">National H2H:</span> {inspector.national_h2h_score ?? "—"}</div>
                  <div><span className="text-muted-foreground">Injury impact:</span> {inspector.injury_impact ?? "—"}</div>
                  <div><span className="text-muted-foreground">Consensus:</span> {inspector.consensus_strength ?? "—"}</div>
                  <div><span className="text-muted-foreground">Actual:</span> {inspector.final_score || inspector.actual_result || "pending"}</div>
                  <div>
                    <span className="text-muted-foreground">Evaluation:</span>{" "}
                    <span className={STATUS_COLORS[inspector.status_color]?.split(" ")[1]}>{inspector.evaluation_status}</span>
                  </div>
                </div>
                {inspector.reason_analysis?.length > 0 && (
                  <div>
                    <h3 className="font-semibold mb-2">Reason Analysis</h3>
                    <ul className="list-disc pl-5 space-y-1 text-muted-foreground">
                      {inspector.reason_analysis.map((r) => <li key={r}>{r}</li>)}
                    </ul>
                  </div>
                )}
                <details className="rounded-xl border border-white/10 p-3">
                  <summary className="cursor-pointer font-semibold">Full stored payload</summary>
                  <pre className="mt-3 text-xs overflow-x-auto max-h-64 text-muted-foreground">
                    {JSON.stringify(inspector.stored_prediction, null, 2)}
                  </pre>
                </details>
              </div>
            )}
          </motion.div>
        </div>
      )}
    </div>
  );
}
