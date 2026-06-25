import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Sparkles, Target } from "lucide-react";

const RISK_STYLES = {
  low: "bg-green-500/15 text-green-300 border-green-500/30",
  medium: "bg-yellow-500/15 text-yellow-200 border-yellow-500/30",
  high: "bg-orange-500/15 text-orange-200 border-orange-500/30",
};

function riskBadge(level) {
  const key = String(level || "medium").toLowerCase();
  return RISK_STYLES[key] || RISK_STYLES.medium;
}

export default function BestPicksPanel({ tips = [], loading }) {
  return (
    <div className="glass rounded-xl p-5 h-full">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-display font-semibold">Best Picks</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Top upcoming opportunities from live predictions</p>
        </div>
        <Link
          to="/matches?status=upcoming"
          className="text-primary text-xs font-medium flex items-center gap-1 hover:underline shrink-0"
        >
          Match Center <ArrowRight className="w-3 h-3" />
        </Link>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="w-6 h-6 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
        </div>
      ) : tips.length === 0 ? (
        <div className="rounded-lg border border-dashed border-white/10 bg-white/[0.02] px-4 py-10 text-center">
          <Target className="w-8 h-8 mx-auto mb-3 text-muted-foreground/50" />
          <p className="text-sm font-medium">No best picks right now</p>
          <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
            Upcoming fixtures need sufficient historical market data and model confidence to rank as best picks.
          </p>
          <Link to="/matches" className="inline-flex items-center gap-1 text-primary text-xs mt-4 hover:underline">
            Browse upcoming matches <ArrowRight className="w-3 h-3" />
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {tips.map((tip) => (
            <div
              key={`${tip.fixture_id}-${tip.market_key}`}
              className="rounded-lg border border-white/10 bg-white/5 p-4 hover:border-primary/30 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold truncate">{tip.match_name}</div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {tip.market} · {tip.prediction}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1.5 shrink-0">
                  <span className="text-xs px-2 py-1 rounded border border-primary/30 bg-primary/10 text-primary font-medium tabular-nums">
                    {tip.confidence}% conf
                  </span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border capitalize ${riskBadge(tip.risk_level)}`}>
                    {tip.risk_level || "upcoming"}
                  </span>
                </div>
              </div>
              {tip.reason && (
                <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{tip.reason}</p>
              )}
              <Link
                to={`/prediction/${tip.fixture_id}`}
                className="inline-flex items-center gap-1 text-primary text-xs mt-3 hover:underline"
              >
                <Sparkles className="w-3 h-3" /> View prediction
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
