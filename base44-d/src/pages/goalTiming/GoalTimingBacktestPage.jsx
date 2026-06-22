import React from "react";
import GoalTimingPageShell from "@/components/goalTiming/GoalTimingPageShell";

export default function GoalTimingBacktestPage() {
  return (
    <GoalTimingPageShell
      title="Goal Timing Backtest"
      subtitle="Historical backtest from 2 years ago to today with strict point-in-time features and no future leakage."
      showComingSoonFooter
    />
  );
}
