import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, Timer, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import GoalTimingPageShell from "@/components/goalTiming/GoalTimingPageShell";
import HybridConfidenceDisplay from "@/components/goalTiming/HybridConfidenceDisplay";
import { PredictionCard } from "@/components/terminal";
import { fetchGoalTimingPicks } from "@/api/saasApi";

function PickCard({ pick }) {
  return (
    <div className="space-y-3">
      <PredictionCard pick={pick} match={pick} variant="goal_timing" href={null} />
      {pick.explanation && (
        <p className="text-sm text-[#94A3B8] leading-relaxed px-1">{pick.explanation}</p>
      )}
      <HybridConfidenceDisplay hybrid={pick.hybrid_confidence} />
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
      phase="52E"
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
