import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { BarChart3, Target, CheckCircle, XCircle, Clock, RefreshCw, AlertCircle, History } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { fetchPerformanceSummary, fetchBestTips } from "@/api/saasApi";
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
  if (s === "unavailable") return "Unavailable";
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

function reliabilityBadge(level) {
  const s = String(level || "low").toLowerCase();
  if (s === "high") return "bg-green-500/15 text-green-300 border-green-500/30";
  if (s === "medium") return "bg-yellow-500/15 text-yellow-200 border-yellow-500/30";
  return "bg-white/10 text-muted-foreground border-white/10";
}

function mapPerformancePayload(perf) {
  if (!perf) return null;
  return {
    overall_accuracy: perf.overall_accuracy,
    total_predictions: perf.total_evaluated,
    correct_predictions: perf.correct_count,
    wrong_predictions: perf.wrong_count,
    pending_predictions: perf.pending_count,
    accuracy_by_market: (perf.markets || []).map((m) => ({
      market: m.market_name,
      total: m.total,
      correct: m.correct,
      wrong: m.wrong,
      pending: m.pending,
      accuracy: m.accuracy,
      sample_size: m.sample_size,
      reliability_level: m.reliability_level,
    })),
    best_performing_market: perf.best_performing_market,
    worst_performing_market: perf.worst_performing_market,
    market_leaderboard: perf.market_leaderboard || [],
    accuracy_trends: perf.accuracy_trends || {},
    rule_a_monitoring: perf.rule_a_monitoring || {},
    agent_contribution: perf.agent_contribution || {},
    snapshot_count: perf.snapshot_count ?? 0,
    recent_results: perf.recent_results || [],
    updated_at: perf.last_updated,
    data_source: perf.data_source,
    disclaimer: perf.disclaimer,
    version: perf.version,
  };
}

function isEmptySummary(data) {
  if (!data) return true;
  const settled = (data.correct_predictions || 0) + (data.wrong_predictions || 0);
  return settled === 0 && (data.data_source === "empty" || !data.overall_accuracy);
}

export default function AccuracyCenter() {
  const [data, setData] = useState(null);
  const [bestTips, setBestTips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [usingDemo, setUsingDemo] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setUsingDemo(false);
    try {
      const [perf, tipsPayload] = await Promise.all([
        fetchPerformanceSummary(),
        fetchBestTips({ limit: 8 }),
      ]);
      const mapped = mapPerformancePayload(perf);
      setBestTips(tipsPayload?.tips || []);
      if (isEmptySummary(mapped) && import.meta.env.DEV) {
        setData(DEV_ACCURACY_DEMO);
        setUsingDemo(true);
      } else {
        setData(mapped);
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
    .filter((m) => m.accuracy != null && (m.sample_size ?? m.total ?? 0) >= 20)
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
          <h1 className="text-2xl font-display font-bold">Performance Center</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Platform prediction performance on finished matches.
          </p>
          <p className="text-xs text-muted-foreground mt-2">
            Accuracy is calculated from finished matches only. Results are checked automatically every 30 minutes after matches finish.
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
              <h2 className="font-display font-semibold mb-4">Accuracy Trend</h2>
              <dl className="space-y-2 text-sm">
                {[
                  ["Last 7 days", data.accuracy_trends?.last_7_days],
                  ["Last 30 days", data.accuracy_trends?.last_30_days],
                  ["All time", data.accuracy_trends?.all_time],
                ].map(([label, trend]) => (
                  <div key={label} className="flex justify-between border-b border-white/5 pb-2">
                    <dt className="text-muted-foreground">{label}</dt>
                    <dd className="text-right">
                      <span className="font-medium">{pct(trend?.winrate)}</span>
                      <span className="text-xs text-muted-foreground ml-2">
                        n={trend?.evaluated_count ?? 0}
                      </span>
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="text-xs text-muted-foreground mt-3">Snapshots: {data.snapshot_count ?? 0}</p>
            </div>

            <div className="glass rounded-xl p-5">
              <h2 className="font-display font-semibold mb-4">Rule A Monitoring</h2>
              {data.rule_a_monitoring?.settled_1x2 > 0 ? (
                <dl className="space-y-2 text-sm">
                  <div className="flex justify-between"><dt className="text-muted-foreground">WDE preserved</dt><dd>{data.rule_a_monitoring.wde_preserved ?? 0}</dd></div>
                  <div className="flex justify-between"><dt className="text-muted-foreground">Scoreline override</dt><dd>{data.rule_a_monitoring.scoreline_override ?? 0}</dd></div>
                  <div className="flex justify-between"><dt className="text-muted-foreground">Override rate</dt><dd>{pct(data.rule_a_monitoring.override_rate)}</dd></div>
                  <div className="flex justify-between"><dt className="text-muted-foreground">Beneficial</dt><dd className="text-green-400">{data.rule_a_monitoring.beneficial_override ?? 0}</dd></div>
                  <div className="flex justify-between"><dt className="text-muted-foreground">Harmful</dt><dd className="text-red-400">{data.rule_a_monitoring.harmful_override ?? 0}</dd></div>
                </dl>
              ) : (
                <p className="text-sm text-muted-foreground">Rule A telemetry will appear after settled 1X2 evaluations with harmonization metadata.</p>
              )}
            </div>
          </div>

          {(data.market_leaderboard || []).length > 0 && (
            <div className="glass rounded-xl p-5">
              <h2 className="font-display font-semibold mb-4">Market Leaderboard</h2>
              <div className="space-y-2">
                {data.market_leaderboard.map((m) => (
                  <div key={m.market_name} className="flex items-center justify-between text-sm border-b border-white/5 pb-2">
                    <span>#{m.rank} {m.market_name}</span>
                    <span>
                      {pct(m.winrate)}
                      <span className="text-xs text-muted-foreground ml-2">n={m.sample_size}</span>
                      <span className={`ml-2 px-1.5 py-0.5 rounded text-[10px] border ${reliabilityBadge(m.reliability)}`}>{m.reliability}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

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
                  <div key={m.market} className="flex items-center justify-between text-sm border-b border-white/5 pb-2 gap-2">
                    <span className="text-muted-foreground">{m.market}</span>
                    <span className="text-right">
                      {(m.sample_size ?? m.total ?? 0) >= 20 ? (
                        pct(m.accuracy)
                      ) : (
                        <span className="text-yellow-300/90">Insufficient data</span>
                      )}
                      <span className="text-xs text-muted-foreground ml-2">
                        from {m.sample_size ?? m.total ?? 0} evaluated
                      </span>
                      {m.reliability_level && (
                        <span className={`ml-2 px-1.5 py-0.5 rounded text-[10px] border ${reliabilityBadge(m.reliability_level)}`}>
                          {m.reliability_level}
                        </span>
                      )}
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
                  <dt className="text-muted-foreground">Best market</dt>
                  <dd className="font-medium">{data.best_performing_market || "—"}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Weakest market</dt>
                  <dd className="font-medium">{data.worst_performing_market || "—"}</dd>
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
            <h2 className="font-display font-semibold mb-4">Best Tips</h2>
            {bestTips.length === 0 ? (
              <p className="text-sm text-muted-foreground">No safe best tips on upcoming fixtures right now.</p>
            ) : (
              <div className="space-y-3">
                {bestTips.map((tip) => (
                  <div key={`${tip.fixture_id}-${tip.market_key}`} className="rounded-lg border border-white/10 p-4 bg-white/5">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="font-semibold">{tip.match_name}</div>
                        <div className="text-xs text-muted-foreground mt-1">{formatDate(tip.match_date)}</div>
                      </div>
                      <span className="text-xs px-2 py-1 rounded border border-primary/30 bg-primary/10 text-primary">
                        score {tip.best_tip_score}
                      </span>
                    </div>
                    <div className="mt-3 grid sm:grid-cols-2 gap-2 text-sm">
                      <div>
                        <span className="text-muted-foreground">Market:</span> {tip.market}
                      </div>
                      <div>
                        <span className="text-muted-foreground">Pick:</span> {tip.prediction}
                      </div>
                      <div>
                        <span className="text-muted-foreground">Confidence:</span> {tip.confidence}%
                      </div>
                      <div>
                        <span className="text-muted-foreground">Historical:</span> {pct(tip.historical_market_accuracy)} ({tip.sample_size} samples)
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground mt-2">{tip.reason}</p>
                  </div>
                ))}
              </div>
            )}
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
