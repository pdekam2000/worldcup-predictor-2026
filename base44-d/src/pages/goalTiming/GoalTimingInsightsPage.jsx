import React from "react";
import GoalTimingPageShell from "@/components/goalTiming/GoalTimingPageShell";

export default function GoalTimingInsightsPage() {
  return (
    <GoalTimingPageShell
      title="Goal Timing Model Insights"
      subtitle="Specialist agent breakdown, confidence filters, league/team performance, and recommended production thresholds."
      showComingSoonFooter
    />
  );
}
