import React from "react";

import { Link } from "react-router-dom";

import { ArrowRight } from "lucide-react";



const GOAL_TIMING_LINKS = [

  { label: "Today's Picks", path: "/goal-timing/picks" },

  { label: "History", path: "/goal-timing/history" },

  { label: "Accuracy", path: "/goal-timing/accuracy" },

  { label: "Performance", path: "/goal-timing/performance" },

  { label: "Backtest", path: "/goal-timing/backtest" },

  { label: "Model Insights", path: "/goal-timing/insights" },

];



export default function GoalTimingPageShell({

  title,

  subtitle,

  children,

  phase = "52E",

  showComingSoonFooter = false,

}) {

  return (

    <div className="space-y-6 max-w-6xl mx-auto">

      <div>

        <p className="terminal-section-title mb-1">Elite Goal Timing · EGIE</p>

        <h1 className="text-2xl sm:text-3xl font-display font-bold text-[#F8FAFC]">{title}</h1>

        {subtitle && (

          <p className="text-sm mt-1 max-w-2xl text-[#94A3B8]">{subtitle}</p>

        )}

      </div>



      <div className="flex flex-wrap gap-2">

        {GOAL_TIMING_LINKS.map((link) => (

          <Link

            key={link.path}

            to={link.path}

            className="text-xs px-3 py-1.5 rounded-full border border-white/[0.08] bg-[#101827] text-[#94A3B8] hover:border-[#00E676]/30 hover:text-[#00E676] transition-colors"

          >

            {link.label}

          </Link>

        ))}

      </div>



      {children}



      {showComingSoonFooter && (

        <div className="terminal-card border-dashed border-white/10 p-6 text-center">

          <p className="text-sm text-[#94A3B8]">

            Goal timing predictions and evaluation results appear here when available.

          </p>

          <Link

            to="/goal-timing/dashboard"

            className="inline-flex items-center gap-1 text-[#00E676] text-sm font-medium mt-3 hover:underline"

          >

            Back to Dashboard <ArrowRight className="w-3.5 h-3.5" />

          </Link>

        </div>

      )}

    </div>

  );

}


