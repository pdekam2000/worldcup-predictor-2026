import React, { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Brain, TrendingUp, TrendingDown, FileText, RefreshCw, Target, Activity } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, Legend, CartesianGrid,
} from "recharts";
import { Button } from "@/components/ui/button";
import {
  fetchAdminLearningDashboard,
  generateAdminLearningReport,
  fetchAdminLearningReports,
} from "@/api/saasApi";

function pct(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return `${Math.round(Number(v) * 1000) / 10}%`;
}

function settledLabel(row) {
  const denom = row?.settled ?? row?.total;
  return `${row?.correct ?? 0}/${denom ?? 0}`;
}

function MetricTable({ title, rows, icon: Icon }) {
  return (
    <div className="glass rounded-xl p-4">
      <h3 className="font-semibold flex items-center gap-2 mb-3">
        {Icon && <Icon className="w-4 h-4 text-primary" />} {title}
      </h3>
      <div className="space-y-2">
        {(rows || []).slice(0, 10).map((row) => (
          <div key={row.key || row.label} className="flex justify-between text-sm">
            <span className="text-muted-foreground">{row.label || row.key}</span>
            <span className="font-medium">
              {pct(row.winrate)}{" "}
              <span className="text-xs text-muted-foreground">({settledLabel(row)})</span>
            </span>
          </div>
        ))}
        {(!rows || rows.length === 0) && (
          <p className="text-xs text-muted-foreground">Insufficient settled data.</p>
        )}
      </div>
    </div>
  );
}

function PerformanceBarChart({ title, data, dataKey = "winrate", labelKey = "label" }) {
  const chartData = useMemo(
    () => (data || []).map((row) => ({
      name: (row[labelKey] || row.key || "").slice(0, 14),
      winrate: row.winrate != null ? Math.round(row.winrate * 1000) / 10 : null,
      settled: row.settled ?? row.total ?? 0,
    })),
    [data, labelKey],
  );

  return (
    <div className="glass rounded-xl p-4">
      <h3 className="font-semibold mb-3">{title}</h3>
      {chartData.length === 0 ? (
        <p className="text-xs text-muted-foreground">Insufficient settled data.</p>
      ) : (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 24 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={50} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} unit="%" />
              <Tooltip
                formatter={(v) => (v != null ? `${v}%` : "—")}
                contentStyle={{ background: "rgba(15,15,20,0.95)", border: "1px solid rgba(255,255,255,0.1)" }}
              />
              <Bar dataKey="winrate" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function CalibrationChart({ rows }) {
  const chartData = useMemo(
    () => (rows || [])
      .filter((r) => r.expected_winrate != null && r.winrate != null)
      .map((r) => ({
        bucket: r.label || r.key,
        expected: Math.round((r.expected_winrate || 0) * 1000) / 10,
        actual: Math.round((r.winrate || 0) * 1000) / 10,
        assessment: r.assessment,
      })),
    [rows],
  );

  return (
    <div className="glass rounded-xl p-4">
      <h3 className="font-semibold mb-3 flex items-center gap-2">
        <Activity className="w-4 h-4 text-primary" /> Confidence Calibration
      </h3>
      {chartData.length === 0 ? (
        <p className="text-xs text-muted-foreground">Need settled predictions per bucket.</p>
      ) : (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
              <XAxis dataKey="bucket" tick={{ fontSize: 10 }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} unit="%" />
              <Tooltip
                formatter={(v) => `${v}%`}
                contentStyle={{ background: "rgba(15,15,20,0.95)", border: "1px solid rgba(255,255,255,0.1)" }}
              />
              <Legend />
              <Line type="monotone" dataKey="expected" name="Expected" stroke="#94a3b8" strokeDasharray="4 4" dot={false} />
              <Line type="monotone" dataKey="actual" name="Actual" stroke="hsl(var(--primary))" strokeWidth={2} dot />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="mt-3 space-y-1 text-xs text-muted-foreground">
        {(rows || []).slice(0, 6).map((r) => (
          <div key={r.label || r.key}>
            {r.summary || `${r.label}: ${pct(r.winrate)} (${r.assessment || "n/a"})`}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AdminLearningDashboard() {
  const [dashboard, setDashboard] = useState(null);
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dash, reps] = await Promise.all([
        fetchAdminLearningDashboard(),
        fetchAdminLearningReports({ limit: 5 }),
      ]);
      setDashboard(dash);
      setReports(reps.reports || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load learning dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onGenerate = async () => {
    try {
      await generateAdminLearningReport(undefined, "v2");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Report generation failed");
    }
  };

  const opt = dashboard?.optimization;
  const recs = dashboard?.recommendations || {};
  const sample = opt?.sample_size || {};

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-display font-bold flex items-center gap-2">
            <Brain className="w-6 h-6 text-primary" /> Learning Dashboard
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Phase 35 accuracy-driven optimization — advisory only, no automatic model changes.
          </p>
        </div>
        <Button type="button" size="sm" onClick={onGenerate}>
          <RefreshCw className="w-4 h-4 mr-2" /> Generate V2 Report
        </Button>
      </div>

      {error && <div className="glass rounded-xl p-3 text-sm text-red-300">{error}</div>}
      {dashboard?.disclaimer && (
        <p className="text-xs text-yellow-200/70 border border-yellow-500/20 rounded-lg p-3">{dashboard.disclaimer}</p>
      )}

      {(dashboard?.insufficient_data || opt?.insufficient_data) && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          {dashboard?.trust_message || opt?.trust_message || "Learning insights require at least 20 evaluated real predictions."}
          {" "}
          (Settled: {dashboard?.settled_evaluations ?? opt?.sample_size?.settled ?? 0})
        </div>
      )}

      {opt && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "Evaluations", value: sample.evaluations ?? 0 },
            { label: "Settled", value: sample.settled ?? 0 },
            { label: "Pending", value: sample.pending ?? 0 },
            { label: "Schema", value: opt.schema_version || "35-v1" },
          ].map((s) => (
            <div key={s.label} className="glass rounded-xl p-3 text-center">
              <p className="text-xs text-muted-foreground">{s.label}</p>
              <p className="text-xl font-bold">{s.value}</p>
            </div>
          ))}
        </motion.div>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <PerformanceBarChart
          title="Confidence Bucket Performance"
          data={opt?.confidence_bucket_analysis || dashboard?.confidence_bucket_performance}
        />
        <PerformanceBarChart
          title="Market Performance"
          data={opt?.market_analysis || dashboard?.market_performance}
        />
        <PerformanceBarChart
          title="Recommendation Performance"
          data={opt?.recommendation_analysis || dashboard?.recommendation_performance}
        />
        <PerformanceBarChart
          title="Agent Ranking"
          data={opt?.agent_analysis || dashboard?.agent_performance}
        />
      </div>

      <CalibrationChart rows={opt?.calibration_audit} />

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        <MetricTable title="Top Agents" rows={opt?.top_agents || dashboard?.top_agents} icon={TrendingUp} />
        <MetricTable title="Weakest Agents" rows={opt?.weakest_agents || dashboard?.worst_agents} icon={TrendingDown} />
        <MetricTable title="Best Markets" rows={opt?.best_markets || dashboard?.best_markets} icon={Target} />
      </div>

      {opt?.recommendation_quality_audit && (
        <div className="glass rounded-xl p-4">
          <h3 className="font-semibold mb-3">Official vs Caution · Safe / Value / Aggressive</h3>
          <div className="grid md:grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground mb-1">Official Picks</p>
              <p className="font-medium">{pct(opt.recommendation_quality_audit.official_vs_caution?.official?.winrate)}</p>
            </div>
            <div>
              <p className="text-muted-foreground mb-1">Caution Picks</p>
              <p className="font-medium">{pct(opt.recommendation_quality_audit.official_vs_caution?.caution?.winrate)}</p>
            </div>
            <div>
              <p className="text-muted-foreground mb-1">Strongest Category</p>
              <p className="font-medium">
                {opt.recommendation_quality_audit.strongest_category?.label || "—"}
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <div className="glass rounded-xl p-4">
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-green-400" /> Improvement Suggestions (V2)
          </h3>
          <ul className="text-sm space-y-2 text-muted-foreground">
            {(opt?.improvement_suggestions || recs.suggested_weight_increases || []).map((r) => (
              <li key={r}>• {r}</li>
            ))}
            {!(opt?.improvement_suggestions || recs.suggested_weight_increases || []).length && <li>None yet.</li>}
          </ul>
        </div>
        <div className="glass rounded-xl p-4">
          <h3 className="font-semibold mb-3">Insights</h3>
          <ul className="text-sm space-y-2 text-muted-foreground">
            {opt?.insights?.confidence_correlates_with_reality != null && (
              <li>
                • Confidence correlates with reality:{" "}
                {opt.insights.confidence_correlates_with_reality ? "Yes" : "No / inconclusive"}
              </li>
            )}
            {opt?.insights?.best_market && <li>• Best market: {opt.insights.best_market}</li>}
            {opt?.insights?.strongest_recommendation && (
              <li>• Strongest recommendation: {opt.insights.strongest_recommendation}</li>
            )}
            {opt?.insights?.top_agent && <li>• Top agent: {opt.insights.top_agent}</li>}
            {(opt?.insights?.overconfident_buckets || []).length > 0 && (
              <li>• Overconfident buckets: {opt.insights.overconfident_buckets.join(", ")}</li>
            )}
          </ul>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="glass rounded-xl p-4">
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-green-400" /> Suggested Weight Increases
          </h3>
          <ul className="text-sm space-y-2 text-muted-foreground">
            {(recs.suggested_weight_increases || []).map((r) => <li key={r}>• {r}</li>)}
            {!(recs.suggested_weight_increases || []).length && <li>None yet.</li>}
          </ul>
        </div>
        <div className="glass rounded-xl p-4">
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <TrendingDown className="w-4 h-4 text-red-400" /> Suggested Weight Decreases
          </h3>
          <ul className="text-sm space-y-2 text-muted-foreground">
            {(recs.suggested_weight_decreases || []).map((r) => <li key={r}>• {r}</li>)}
            {!(recs.suggested_weight_decreases || []).length && <li>None yet.</li>}
          </ul>
        </div>
      </div>

      <div className="glass rounded-xl p-4">
        <h3 className="font-semibold mb-3 flex items-center gap-2">
          <FileText className="w-4 h-4" /> Stored Reports
        </h3>
        <div className="space-y-2 text-sm">
          {reports.map((r) => (
            <div key={r.id} className="flex justify-between border-b border-white/5 py-2">
              <span>#{r.id} — {r.report_type}</span>
              <span className="text-muted-foreground">{r.created_at?.slice(0, 19)}</span>
            </div>
          ))}
          {reports.length === 0 && <p className="text-muted-foreground">No reports stored yet.</p>}
        </div>
      </div>
    </div>
  );
}
