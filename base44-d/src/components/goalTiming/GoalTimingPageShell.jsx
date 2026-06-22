import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

const GOAL_TIMING_LINKS = [
  { label: "Today's Picks", path: "/goal-timing/picks" },
  { label: "History", path: "/goal-timing/history" },
  { label: "Backtest", path: "/goal-timing/backtest" },
  { label: "Model Insights", path: "/goal-timing/insights" },
];

export default function GoalTimingPageShell({
  title,
  subtitle,
  children,
  phase = "51B",
  showComingSoonFooter = false,
}) {
  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-primary mb-1">
          Elite Goal Timing · Phase {phase}
        </p>
        <h1 className="text-2xl font-display font-bold">{title}</h1>
        {subtitle && (
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">{subtitle}</p>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {GOAL_TIMING_LINKS.map((link) => (
          <Link
            key={link.path}
            to={link.path}
            className="text-xs px-3 py-1.5 rounded-full border border-border bg-card hover:border-primary/40 hover:text-primary transition-colors"
          >
            {link.label}
          </Link>
        ))}
      </div>

      {children}

      {showComingSoonFooter && (
      <div className="rounded-xl border border-dashed border-border bg-muted/30 p-6 text-center">
        <p className="text-sm text-muted-foreground">
          Goal timing predictions and green/red evaluation results will appear here once the engine pipeline is live.
        </p>
        <Link
          to="/goal-timing/dashboard"
          className="inline-flex items-center gap-1 text-primary text-sm font-medium mt-3 hover:underline"
        >
          Back to Dashboard <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
      )}
    </div>
  );
}
