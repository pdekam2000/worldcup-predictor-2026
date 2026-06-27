import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { BarChart3, Target, CheckCircle, XCircle, Clock, RefreshCw, AlertCircle, History } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { fetchAccuracySummary } from "@/api/saasApi";
import { DEV_ACCURACY_DEMO } from "@/lib/accuracyDemoData";
import { Button } from "@/components/ui/button";

const chartTooltipStyle = {
  contentStyle: { background: "hsl(222, 47%, 9%)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "12px", fontSize: "12px" },
  itemStyle: { color: "hsl(210, 40%, 98%)" },
  labelStyle: { color: "hsl(215, 20%, 55%)" },
};

function pct(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Math.round(Number(value) * 1000) / 10}%`;
}

function statusBadge(status) {
  const s = String(status || "pending").toLowerCase();
  if (s === "correct") return "bg-green-500/15 text-green-400 border-green-500/30";
  if (s === "wrong") return "bg-red-500/15 text-red-400 border-red-500/30";
  return "bg-yellow-500/10 text-yellow-300 border-yellow-500/20";
}

function statusLabel(status) {
  const s = String(status || "pending").toLowerCase();
  if (s === "correct") return "Correct";
  if (s === "wrong") return "Wrong";
  return "Pending";
}

function formatDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return "—";
  }
}

function isEmptySummary(data) {
  if (!data) return true;
  const settled = (data.correct_predictions || 0) + (data.wrong_predictions || 0);
  return settled === 0 && data.data_source === "empty";
}

export default function AccuracyCenter() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [usingDemo, setUsingDemo] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setUsingDemo(false);
    try {
      const payload = await fetchAccuracySummary();
      if (isEmptySummary(payload) && import.meta.env.DEV) {
        setData(DEV_ACCURACY_DEMO);
        setUsingDemo(true);
      } else {
        setData(payload);
      }
    } catch (err) {
      if (import.meta.env.DEV) {
        setData(DEV_ACCURACY_DEMO);
        setUsingDemo(true);
      } else {
        setError(err instanceof Error ? err.message : "Failed to load accuracy data");
        setData(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const settled = (data?.correct_predictions || 0) + (data?.wrong_predictions || 0);
  const marketChart = (data?.accuracy_by_market || [])
    .filter((m) => m.accuracy != null && (m.total || 0) > 0)
    .map((m) => ({
      market: m.market,
      accuracy: Math.round(Number(m.accuracy) * 1000) / 10,
    }));

  const stats = [
    { label: "Overall Accuracy", value: pct(data?.overall_accuracy), icon: Target, color: "text-green-400", bg: "bg-green-500/10" },
    { label: "Correct", value: String(data?.correct_predictions ?? 0), icon: CheckCircle, color: "text-green-400", bg: "bg-green-500/10" },
    { label: "Wrong", value: String(data?.wrong_predictions ?? 0), icon: XCircle, color: "text-red-400", bg: "bg-red-500/10" },
    { label: "Pending", value: String(data?.pending_predictions ?? 0), icon: Clock, color: "text-yellow-400", bg: "bg-yellow-500/10" },
  ];

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-display font-bold">Accuracy Center</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Platform prediction performance on finished matches.
          </p>
          <p className="text-xs text-muted-foreground mt-2">
            Accuracy is calculated from finished matches only.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} className="border-white/10 rounded-lg">
          <RefreshCw className="w-4 h-4 mr-2" /> Refresh
        </Button>
      </div>

      {usingDemo && (
        <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-200">
          Demo data — no evaluated predictions in backend yet (dev mode only).
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {!error && settled === 0 && !usingDemo && (
        <div className="glass rounded-xl p-8 text-center">
          <BarChart3 className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
          <h2 className="font-display font-semibold text-lg">No completed prediction evaluations yet</h2>
          <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
            Once finished matches are evaluated against stored predictions, platform accuracy will appear here.
          </p>
          <Link to="/history" className="inline-flex items-center gap-2 text-primary text-sm mt-4 hover:underline">
            <History className="w-4 h-4" /> View your personal prediction history
          </Link>
        </div>
      )}

      {(settled > 0 || usingDemo) && data && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {stats.map((s, i) => (
              <motion.div key={s.label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="glass rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-muted-foreground">{s.label}</span>
                  <div className={`w-8 h-8 rounded-lg ${s.bg} flex items-center justify-center`}>
                    <s.icon className={`w-4 h-4 ${s.color}`} />
                  </div>
                </div>
                <div className="text-2xl font-display font-bold">{s.value}</div>
              </motion.div>
            ))}
          </div>

          <div className="grid lg:grid-cols-2 gap-6">
            <div className="glass rounded-xl p-5">
              <h2 className="font-display font-semibold mb-4">Accuracy by Market</h2>
              {marketChart.length === 0 ? (
                <p className="text-sm text-muted-foreground">No market-level evaluations yet.</p>
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={marketChart} layout="vertical" margin={{ left: 8, right: 16 }}>
                    <XAxis type="number" domain={[0, 100]} tick={{ fill: "hsl(215, 20%, 55%)", fontSize: 12 }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="market" width={110} tick={{ fill: "hsl(215, 20%, 55%)", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip {...chartTooltipStyle} formatter={(v) => [`${v}%`, "Accuracy"]} />
                    <Bar dataKey="accuracy" radius={[0, 6, 6, 0]} barSize={22}>
                      {marketChart.map((entry) => (
                        <Cell key={entry.market} fill={entry.accuracy >= 50 ? "hsl(142, 71%, 45%)" : "hsl(0, 72%, 51%)"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
              <div className="mt-4 space-y-2">
                {(data.accuracy_by_market || []).map((m) => (
                  <div key={m.market} className="flex items-center justify-between text-sm border-b border-white/5 pb-2">
                    <span className="text-muted-foreground">{m.market}</span>
                    <span>
                      {pct(m.accuracy)}
                      <span className="text-xs text-muted-foreground ml-2">
                        ({m.correct}/{m.total || 0})
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="glass rounded-xl p-5">
              <h2 className="font-display font-semibold mb-2">Summary</h2>
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Total stored predictions</dt>
                  <dd className="font-medium">{data.total_predictions ?? 0}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Evaluated (correct + wrong)</dt>
                  <dd className="font-medium">{settled}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Data source</dt>
                  <dd className="font-medium text-xs">{data.data_source || "—"}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Updated</dt>
                  <dd className="font-medium text-xs">{formatDate(data.updated_at)}</dd>
                </div>
              </dl>
              <p className="text-xs text-muted-foreground mt-4 pt-4 border-t border-white/10">
                {data.disclaimer || "Accuracy is calculated from finished matches only."}
              </p>
              <Link to="/history" className="inline-flex items-center gap-2 text-primary text-sm mt-4 hover:underline">
                <History className="w-4 h-4" /> Your personal history
              </Link>
            </div>
          </div>

          <div className="glass rounded-xl p-5">
            <h2 className="font-display font-semibold mb-4">Recent Evaluated Predictions</h2>
            {(data.recent_results || []).length === 0 ? (
              <p className="text-sm text-muted-foreground">No recent evaluations.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-muted-foreground text-xs">
                      <th className="pb-3 font-medium">Match</th>
                      <th className="pb-3 font-medium">Market</th>
                      <th className="pb-3 font-medium">Prediction</th>
                      <th className="pb-3 font-medium">Actual</th>
                      <th className="pb-3 font-medium">Confidence</th>
                      <th className="pb-3 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {data.recent_results.map((r, i) => (
                      <tr key={`${r.fixture_id}-${r.market}-${i}`} className="hover:bg-white/5">
                        <td className="py-3 font-medium">
                          <Link to={`/prediction/${r.fixture_id}`} className="hover:text-primary">
                            {r.match_name}
                          </Link>
                          <div className="text-xs text-muted-foreground">{formatDate(r.match_date)}</div>
                        </td>
                        <td className="py-3 text-muted-foreground">{r.market}</td>
                        <td className="py-3">{r.prediction || "—"}</td>
                        <td className="py-3 text-muted-foreground">{r.actual_result || r.final_score || "—"}</td>
                        <td className="py-3">{r.confidence != null ? `${Math.round(r.confidence)}%` : "—"}</td>
                        <td className="py-3">
                          <span className={`px-2 py-1 rounded-md text-xs font-medium border ${statusBadge(r.status)}`}>
                            {statusLabel(r.status)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
