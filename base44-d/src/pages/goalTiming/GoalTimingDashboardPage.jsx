import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Timer, Target, History, LineChart, Brain, ArrowRight } from "lucide-react";
import GoalTimingPageShell from "@/components/goalTiming/GoalTimingPageShell";
import { fetchGoalTimingStatus, fetchGoalTimingDashboard } from "@/api/saasApi";

const SECTIONS = [
  {
    icon: Target,
    title: "Today's Picks",
    path: "/goal-timing/picks",
    desc: "First goal team and minute-range picks for today's fixtures.",
  },
  {
    icon: History,
    title: "History",
    path: "/goal-timing/history",
    desc: "Evaluated goal timing predictions with correct/wrong/partial status.",
  },
  {
    icon: LineChart,
    title: "Backtest",
    path: "/goal-timing/backtest",
    desc: "2-year leakage-safe historical performance analysis.",
  },
  {
    icon: Brain,
    title: "Model Insights",
    path: "/goal-timing/insights",
    desc: "Confidence buckets, specialist agents, and data quality impact.",
  },
];

export default function GoalTimingDashboardPage() {
  const [status, setStatus] = useState(null);
  const [dashboard, setDashboard] = useState(null);

  useEffect(() => {
    Promise.all([
      fetchGoalTimingStatus().catch(() => null),
      fetchGoalTimingDashboard().catch(() => null),
    ]).then(([st, dash]) => {
      setStatus(st);
      setDashboard(dash);
    });
  }, []);

  const picks = dashboard?.picks_today || [];

  return (
    <GoalTimingPageShell
      title="Goal Timing Dashboard"
      subtitle="Central hub for elite first-goal and goal-timing intelligence. Independent from legacy 1X2 archive."
      phase={status?.phase || "51D"}
    >
      <div className="glass rounded-xl p-5 border border-primary/15">
        <div className="flex items-start gap-3">
          <Timer className="w-8 h-8 text-primary shrink-0 mt-0.5" />
          <div>
            <h2 className="font-semibold">Engine status</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {status?.message || "Loading engine status…"}
            </p>
            {status?.prediction_leagues?.length > 0 && (
              <p className="text-xs text-muted-foreground mt-1">
                Active leagues: {status.prediction_leagues.join(", ")}
              </p>
            )}
          </div>
        </div>
      </div>

      {picks.length > 0 && (
        <div className="glass rounded-xl p-5 border border-primary/15 space-y-3">
          <h2 className="font-semibold">Today's Premier League picks</h2>
          <ul className="space-y-2 text-sm">
            {picks.slice(0, 5).map((pick) => (
              <li key={pick.fixture_id} className="flex justify-between gap-3 border-b border-border/50 pb-2 last:border-0">
                <span>
                  {pick.home_team} vs {pick.away_team}
                </span>
                <span className="text-muted-foreground shrink-0">
                  {pick.first_goal_time_range} · {Math.round((pick.confidence_score || 0) * 100)}%
                </span>
              </li>
            ))}
          </ul>
          <Link to="/goal-timing/picks" className="text-xs text-primary font-medium inline-flex items-center gap-1">
            View all picks <ArrowRight className="w-3 h-3" />
          </Link>
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-4">
        {SECTIONS.map(({ icon: Icon, title, path, desc }) => (
          <Link
            key={path}
            to={path}
            className="glass rounded-xl p-5 hover:border-primary/30 hover:shadow-md transition-all group"
          >
            <Icon className="w-6 h-6 text-primary mb-3" />
            <h3 className="font-semibold group-hover:text-primary transition-colors">{title}</h3>
            <p className="text-sm text-muted-foreground mt-1">{desc}</p>
            <span className="inline-flex items-center gap-1 text-xs text-primary font-medium mt-3">
              Open <ArrowRight className="w-3 h-3" />
            </span>
          </Link>
        ))}
      </div>
    </GoalTimingPageShell>
  );
}
