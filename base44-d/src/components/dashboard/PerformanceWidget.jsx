import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, BarChart3, Target } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { formatPct } from "@/lib/archiveStatus";

const chartTooltipStyle = {
  contentStyle: {
    background: "hsl(222, 47%, 9%)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: "12px",
    fontSize: "12px",
  },
  itemStyle: { color: "hsl(210, 40%, 98%)" },
  labelStyle: { color: "hsl(215, 20%, 55%)" },
};

const BAR_COLORS = ["hsl(217, 91%, 60%)", "hsl(142, 71%, 45%)", "hsl(38, 92%, 50%)", "hsl(280, 65%, 60%)"];

export default function PerformanceWidget({ perf, loading }) {
  const evaluated = (perf?.correct_count ?? 0) + (perf?.wrong_count ?? 0);
  const marketChart = (perf?.markets || [])
    .filter((m) => m.accuracy != null && (m.sample_size ?? m.total ?? 0) > 0)
    .slice(0, 6)
    .map((m) => ({
      market: m.market_name,
      accuracy: Math.round(Number(m.accuracy) * 1000) / 10,
      sample: m.sample_size ?? m.total ?? 0,
    }));

  return (
    <div className="glass rounded-xl p-5 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-display font-semibold">Platform Accuracy</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Evaluated finished matches only</p>
        </div>
        <Link
          to="/analytics/accuracy"
          className="text-primary text-xs font-medium flex items-center gap-1 hover:underline shrink-0"
        >
          Analytics <ArrowRight className="w-3 h-3" />
        </Link>
      </div>

      {loading ? (
        <div className="flex justify-center py-12 flex-1">
          <div className="w-6 h-6 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
        </div>
      ) : evaluated === 0 ? (
        <div className="rounded-lg border border-dashed border-white/10 bg-white/[0.02] px-4 py-10 text-center flex-1 flex flex-col items-center justify-center">
          <Target className="w-8 h-8 mb-3 text-muted-foreground/50" />
          <p className="text-sm font-medium">No evaluated predictions yet</p>
          <p className="text-xs text-muted-foreground mt-1 max-w-xs">
            {perf?.empty_state_message ||
              "Predictions are evaluated automatically after matches finish."}
          </p>
        </div>
      ) : (
        <>
          <div className="flex items-end gap-4 mb-4">
            <div>
              <div className="text-3xl font-display font-bold tabular-nums">
                {formatPct(perf?.overall_accuracy)}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                {perf?.correct_count ?? 0} correct · {perf?.wrong_count ?? 0} wrong
              </div>
            </div>
            {perf?.best_performing_market && (
              <div className="text-xs text-muted-foreground ml-auto text-right">
                <span className="block text-[10px] uppercase tracking-wide">Best market</span>
                <span className="text-foreground font-medium">{perf.best_performing_market}</span>
              </div>
            )}
          </div>

          {marketChart.length > 0 ? (
            <div className="flex-1 min-h-[180px]" translate="no">
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={marketChart} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <XAxis
                    dataKey="market"
                    tick={{ fill: "hsl(215, 20%, 55%)", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    interval={0}
                    angle={-25}
                    textAnchor="end"
                    height={50}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fill: "hsl(215, 20%, 55%)", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    unit="%"
                  />
                  <Tooltip
                    {...chartTooltipStyle}
                    formatter={(value, _name, props) => [
                      `${value}% (n=${props.payload.sample})`,
                      "Accuracy",
                    ]}
                  />
                  <Bar dataKey="accuracy" radius={[6, 6, 0, 0]}>
                    {marketChart.map((entry, index) => (
                      <Cell key={entry.market} fill={BAR_COLORS[index % BAR_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-xs text-muted-foreground py-4">
              <BarChart3 className="w-4 h-4" />
              Per-market breakdown will appear as more evaluations complete.
            </div>
          )}

          {perf?.disclaimer && (
            <p className="text-[10px] text-muted-foreground mt-3">{perf.disclaimer}</p>
          )}
        </>
      )}
    </div>
  );
}
