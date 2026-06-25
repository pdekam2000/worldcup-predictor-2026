import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import GoalTimingPageShell from "@/components/goalTiming/GoalTimingPageShell";
import HybridConfidenceDisplay from "@/components/goalTiming/HybridConfidenceDisplay";
import { fetchGoalTimingHistory } from "@/api/saasApi";

const STATUS_STYLES = {
  correct: "text-emerald-600 bg-emerald-500/10 border-emerald-500/30",
  wrong: "text-red-600 bg-red-500/10 border-red-500/30",
  partial: "text-amber-600 bg-amber-500/10 border-amber-500/30",
  pending: "text-muted-foreground bg-muted/40 border-border",
};

function StatusPill({ label, value }) {
  const style = STATUS_STYLES[value] || STATUS_STYLES.pending;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border capitalize ${style}`}>
      {label}: {value || "pending"}
    </span>
  );
}

function HistoryCard({ item }) {
  const pred = item.predicted || {};
  const actual = item.actual || {};
  const status = item.status || {};

  const firstGoalLabel =
    pred.first_goal_team === "home"
      ? item.home_team
      : pred.first_goal_team === "away"
        ? item.away_team
        : pred.first_goal_team || "—";

  return (
    <div className="glass rounded-xl p-5 border border-border/80 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            {item.competition_key?.replace(/_/g, " ") || "Premier League"}
          </p>
          <h3 className="font-semibold text-lg mt-0.5">
            {item.home_team} vs {item.away_team}
          </h3>
          {item.match_date && (
            <p className="text-xs text-muted-foreground mt-1">
              {new Date(item.match_date).toLocaleString()}
            </p>
          )}
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-3 text-sm">
        <div className="rounded-lg bg-muted/40 p-3">
          <p className="text-xs text-muted-foreground">Predicted</p>
          <p className="font-medium mt-1">
            {firstGoalLabel} · {pred.first_goal_time_range || "—"}
            {pred.estimated_first_goal_minute != null ? ` · ~${Math.round(pred.estimated_first_goal_minute)}'` : ""}
          </p>
        </div>
        <div className="rounded-lg bg-muted/40 p-3">
          <p className="text-xs text-muted-foreground">Actual</p>
          <p className="font-medium mt-1">
            {actual.first_goal_team === "none"
              ? "No goal"
              : actual.first_goal_team === "home"
                ? item.home_team
                : actual.first_goal_team === "away"
                  ? item.away_team
                  : actual.first_goal_team || "—"}
            {actual.first_goal_time_range ? ` · ${actual.first_goal_time_range}` : ""}
            {actual.first_goal_minute != null ? ` · ${actual.first_goal_minute}'` : ""}
          </p>
        </div>
      </div>

      <HybridConfidenceDisplay
        hybrid={item.hybrid_confidence || pred.hybrid_confidence}
        compact
      />

      <div className="flex flex-wrap gap-2">
        <StatusPill label="Team" value={status.first_goal_team} />
        <StatusPill label="Range" value={status.goal_range} />
        <StatusPill label="Minute" value={status.goal_minute} />
      </div>
    </div>
  );
}

export default function GoalTimingHistoryPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [payload, setPayload] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchGoalTimingHistory({ limit: 50 });
      setPayload(data);
    } catch (err) {
      setError(err?.message || "Failed to load history");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const items = payload?.items || [];

  return (
    <GoalTimingPageShell
      title="Goal Timing History"
      subtitle="Finished match evaluations for the Elite Goal Timing engine — correct, wrong, partial, or pending."
      phase="52E"
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {payload?.total != null ? `${payload.total} evaluation(s) on record` : "Loading…"}
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

      {!loading && !error && items.length === 0 && (
        <div className="rounded-xl border border-dashed border-border bg-muted/30 p-8 text-center">
          <p className="text-sm text-muted-foreground">
            No evaluated matches yet. Evaluations appear after fixtures finish and the learning loop runs.
          </p>
        </div>
      )}

      <div className="space-y-4">
        {items.map((item) => (
          <HistoryCard key={item.evaluation_id || item.fixture_id} item={item} />
        ))}
      </div>
    </GoalTimingPageShell>
  );
}
