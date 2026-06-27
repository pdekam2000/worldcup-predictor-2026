import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Trophy, Target, Archive, X, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { trackEvent } from "@/lib/analytics";
import { TRUST_RESEARCH_ONLY } from "@/lib/trustCopy";

const DISMISS_KEY = "soft_launch_welcome_dismissed";

const STEPS = [
  {
    icon: Trophy,
    title: "Browse Match Center",
    body: "Pick a fixture and run a full multi-market prediction.",
    to: "/matches",
  },
  {
    icon: Target,
    title: "See Best Tips",
    body: "Review program best bets with confidence tiers and explanations.",
    to: "/best-tips",
  },
  {
    icon: Archive,
    title: "Track Results",
    body: "Finished matches appear in Results and Archive with per-market breakdown.",
    to: "/results",
  },
];

export default function SoftLaunchWelcome() {
  const [visible, setVisible] = useState(() => !localStorage.getItem(DISMISS_KEY));

  if (!visible) return null;

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, "1");
    trackEvent("onboarding_welcome_dismissed");
    setVisible(false);
  };

  return (
    <div className="wc-premium-card border-amber-300/50 p-5 sm:p-6 mb-6 relative">
      <button
        type="button"
        onClick={dismiss}
        className="absolute top-3 right-3 p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-amber-50"
        aria-label="Dismiss welcome guide"
      >
        <X className="w-4 h-4" />
      </button>
      <p className="text-xs font-semibold uppercase tracking-wider text-amber-800/70 mb-1">Getting started</p>
      <h2 className="text-lg font-display font-bold text-slate-900 mb-2">Welcome to WorldCup Predictor</h2>
      <p className="text-sm text-slate-600 mb-5 max-w-2xl">
        Three steps to your first experience — {TRUST_RESEARCH_ONLY.toLowerCase()}
      </p>
      <div className="grid sm:grid-cols-3 gap-3">
        {STEPS.map(({ icon: Icon, title, body, to }) => (
          <Link
            key={to}
            to={to}
            onClick={() => trackEvent("onboarding_step_click", { step: to })}
            className="rounded-xl border border-amber-200/70 bg-amber-50/40 p-4 hover:border-amber-300 hover:bg-amber-50 transition-colors group"
          >
            <Icon className="w-5 h-5 text-amber-700 mb-2" />
            <p className="font-semibold text-sm text-slate-900">{title}</p>
            <p className="text-xs text-slate-600 mt-1">{body}</p>
            <span className="inline-flex items-center gap-1 text-xs text-amber-800 font-medium mt-2 group-hover:gap-2 transition-all">
              Open <ArrowRight className="w-3 h-3" />
            </span>
          </Link>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={dismiss} className="border-amber-200">
          Got it
        </Button>
        <Link to="/subscription" className="text-xs text-slate-500 self-center hover:text-amber-800">
          View plans & limits →
        </Link>
      </div>
    </div>
  );
}
