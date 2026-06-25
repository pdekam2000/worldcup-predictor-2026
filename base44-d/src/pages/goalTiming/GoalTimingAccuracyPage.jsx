import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import GoalTimingPageShell from "@/components/goalTiming/GoalTimingPageShell";
import { fetchGoalTimingAccuracy } from "@/api/saasApi";

function pct(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

function MarketCard({ title, stats }) {
  if (!stats) return null;
  return (
    <div className="glass rounded-xl p-5 border border-border/80 space-y-2">
      <h3 className="font-semibold">{title}</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div>
          <p className="text-xs text-muted-foreground">Win rate</p>
          <p className="text-xl font-bold text-primary">{pct(stats.winrate)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Correct</p>
          <p className="font-semibold text-emerald-600">{stats.correct ?? 0}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Wrong</p>
          <p className="font-semibold text-red-600">{stats.wrong ?? 0}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Pending</p>
          <p className="font-semibold">{stats.pending ?? 0}</p>
        </div>
      </div>
      {stats.partial > 0 && (
        <p className="text-xs text-muted-foreground">
          Partial (minute tolerance): {stats.partial} · soft win rate {pct(stats.soft_winrate)}
        </p>
      )}
    </div>
  );
}

export default function GoalTimingAccuracyPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchGoalTimingAccuracy());
    } catch (err) {
      setError(err?.message || "Failed to load accuracy");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const markets = data?.markets || {};

  return (
    <GoalTimingPageShell
      title="Goal Timing Accuracy"
      subtitle="Aggregate win rates for First Goal Team, Goal Range, and Goal Minute markets."
      phase="51E"
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Sample size: {data?.sample_size ?? "—"} evaluated prediction(s)
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
        <MarketCard title="First Goal Team" stats={markets.first_goal_team} />
        <MarketCard title="Goal Range" stats={markets.goal_range} />
        <MarketCard title="Goal Minute" stats={markets.goal_minute} />
      </div>
    </GoalTimingPageShell>
  );
}
