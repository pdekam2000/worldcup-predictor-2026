import React from "react";
import GoalTimingPageShell from "@/components/goalTiming/GoalTimingPageShell";

export default function GoalTimingHistoryPage() {
  return (
    <GoalTimingPageShell
      title="Goal Timing History"
      subtitle="Finished match evaluations for the new engine only — correct, wrong, partial, or pending."
      showComingSoonFooter
    />
  );
}
