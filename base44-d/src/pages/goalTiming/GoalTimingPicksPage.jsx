import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, Timer, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import GoalTimingPageShell from "@/components/goalTiming/GoalTimingPageShell";
import { fetchGoalTimingPicks } from "@/api/saasApi";

function teamLabel(pick, side) {
  if (side === "home") return pick.home_team || "Home";
  if (side === "away") return pick.away_team || "Away";
  return "No clear first scorer";
}

function PickCard({ pick }) {
  const firstGoalLabel =
    pick.first_goal_team === "home"
      ? teamLabel(pick, "home")
      : pick.first_goal_team === "away"
        ? teamLabel(pick, "away")
        : "Unclear";

  return (
    <div className="glass rounded-xl p-5 border border-border/80 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            {pick.competition_key?.replace(/_/g, " ") || "Premier League"}
          </p>
          <h3 className="font-semibold text-lg mt-0.5">
            {pick.home_team} vs {pick.away_team}
          </h3>
          {pick.match_date && (
            <p className="text-xs text-muted-foreground mt-1">
              {new Date(pick.match_date).toLocaleString()}
            </p>
          )}
        </div>
        <Target className="w-5 h-5 text-primary shrink-0" />
      </div>

      <div className="grid sm:grid-cols-3 gap-3 text-sm">
        <div className="rounded-lg bg-muted/40 p-3">
          <p className="text-xs text-muted-foreground">First goal</p>
          <p className="font-medium mt-1">{firstGoalLabel}</p>
        </div>
        <div className="rounded-lg bg-muted/40 p-3">
          <p className="text-xs text-muted-foreground">Minute range</p>
          <p className="font-medium mt-1">{pick.first_goal_time_range || "—"}</p>
        </div>
        <div className="rounded-lg bg-muted/40 p-3">
          <p className="text-xs text-muted-foreground">Est. minute</p>
          <p className="font-medium mt-1">
            {pick.display_estimated_first_goal_minute != null
              ? `~${Math.round(pick.display_estimated_first_goal_minute)}'`
              : pick.estimated_first_goal_minute != null
                ? `~${Math.round(pick.estimated_first_goal_minute)}'`
                : "—"}
          </p>
        </div>
      </div>

      <p className="text-sm text-muted-foreground leading-relaxed">{pick.explanation}</p>

      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
        <span>
          Confidence: <strong className="text-foreground">{Math.round((pick.confidence_score || 0) * 100)}%</strong>
        </span>
        <span>
          Data quality: <strong className="text-foreground">{Math.round((pick.data_quality_score || 0) * 100)}%</strong>
        </span>
        {pick.model_version && (
          <span className="font-mono">{pick.model_version}</span>
        )}
      </div>
    </div>
  );
}

export default function GoalTimingPicksPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [picks, setPicks] = useState([]);
  const [meta, setMeta] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchGoalTimingPicks({ limit: 20 });
      setPicks(data?.picks || []);
      setMeta(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load picks.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <GoalTimingPageShell
      title="Today's Goal Timing Picks"
      subtitle="Premier League first-goal team, minute range, and estimated minute. Stored-data baseline (Phase 51D)."
      phase="51D"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Timer className="w-4 h-4" />
          {meta?.competition_keys?.join(", ") || "premier_league"}
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading && !picks.length && (
        <p className="text-sm text-muted-foreground">Loading goal timing picks…</p>
      )}

      {!loading && !error && picks.length === 0 && (
        <div className="rounded-xl border border-dashed border-border bg-muted/30 p-8 text-center">
          <p className="text-sm text-muted-foreground">
            No Premier League picks available yet. Upcoming fixtures need sufficient stored goal-minute history.
          </p>
        </div>
      )}

      <div className="space-y-4">
        {picks.map((pick) => (
          <PickCard key={`${pick.fixture_id}-${pick.match_date}`} pick={pick} />
        ))}
      </div>
    </GoalTimingPageShell>
  );
}
