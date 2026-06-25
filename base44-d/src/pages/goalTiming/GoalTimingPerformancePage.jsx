import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import GoalTimingPageShell from "@/components/goalTiming/GoalTimingPageShell";
import { fetchGoalTimingPerformance } from "@/api/saasApi";

function pct(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

function BucketTable({ title, buckets }) {
  if (!buckets || Object.keys(buckets).length === 0) return null;
  return (
    <div className="glass rounded-xl p-5 border border-border/80 overflow-x-auto">
      <h3 className="font-semibold mb-3">{title}</h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted-foreground border-b border-border">
            <th className="pb-2 pr-4">Bucket</th>
            <th className="pb-2 pr-4">Win rate</th>
            <th className="pb-2 pr-4">Correct</th>
            <th className="pb-2 pr-4">Wrong</th>
            <th className="pb-2">N</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(buckets).map(([key, stats]) => (
            <tr key={key} className="border-b border-border/50 last:border-0">
              <td className="py-2 pr-4 font-mono text-xs">{key}</td>
              <td className="py-2 pr-4 font-medium">{pct(stats?.winrate)}</td>
              <td className="py-2 pr-4">{stats?.correct ?? 0}</td>
              <td className="py-2 pr-4">{stats?.wrong ?? 0}</td>
              <td className="py-2">{stats?.total ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function GoalTimingPerformancePage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchGoalTimingPerformance());
    } catch (err) {
      setError(err?.message || "Failed to load performance");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const byDq = data?.by_dq_bucket?.first_goal_team || {};
  const byConf = data?.by_confidence_bucket?.first_goal_team || {};
  const byFg = data?.by_predicted_first_goal_team?.first_goal_team || {};
  const leagues = data?.by_league || {};

  return (
    <GoalTimingPageShell
      title="Goal Timing Performance"
      subtitle="Learning statistics — win rate by league, data quality, confidence, and predicted first-goal team."
      phase="51E"
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Sample size: {data?.sample_size ?? "—"}
        </p>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="space-y-4">
        {Object.keys(leagues).length > 0 && (
          <div className="glass rounded-xl p-5 border border-border/80">
            <h3 className="font-semibold mb-3">By league</h3>
            <div className="space-y-3">
              {Object.entries(leagues).map(([league, markets]) => (
                <div key={league} className="text-sm border-b border-border/50 pb-3 last:border-0">
                  <p className="font-medium capitalize mb-1">{league.replace(/_/g, " ")}</p>
                  <p className="text-muted-foreground text-xs">
                    Team {pct(markets?.first_goal_team?.winrate)} · Range {pct(markets?.goal_range?.winrate)} · Minute {pct(markets?.goal_minute?.winrate)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        <BucketTable title="Win rate by DQ bucket (First Goal Team)" buckets={byDq} />
        <BucketTable title="Win rate by confidence bucket (First Goal Team)" buckets={byConf} />
        <BucketTable title="Win rate by predicted first-goal team" buckets={byFg} />
      </div>
    </GoalTimingPageShell>
  );
}
