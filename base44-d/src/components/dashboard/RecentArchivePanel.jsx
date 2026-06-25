import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Archive } from "lucide-react";
import {
  getArchiveStatusConfig,
  resolveArchiveStatus,
  pick1x2Label,
  formatShortDate,
} from "@/lib/archiveStatus";
import MatchTeamsRow from "@/components/match/MatchTeamsRow";

export default function RecentArchivePanel({ items = [], loading }) {
  return (
    <div className="glass rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-display font-semibold">Recent Archive</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Latest system predictions and evaluations</p>
        </div>
        <Link
          to="/history"
          className="text-primary text-xs font-medium flex items-center gap-1 hover:underline"
        >
          Full Archive <ArrowRight className="w-3 h-3" />
        </Link>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="w-6 h-6 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-muted/30 px-4 py-10 text-center">
          <Archive className="w-8 h-8 mx-auto mb-3 text-muted-foreground/50" />
          <p className="text-sm font-medium">No archived predictions yet</p>
          <p className="text-xs text-muted-foreground mt-1">
            Predictions appear here as they are stored and evaluated by the system.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => {
            const statusKey = resolveArchiveStatus(item);
            const cfg = getArchiveStatusConfig(statusKey);
            const Icon = cfg.icon;
            const entryId = item.entry_id || item.id;
            const predicted = item.predicted_1x2 ?? item.prediction_1x2;
            const confidence = item.predicted_confidence ?? item.confidence;
            const inner = (
              <div
                className={`flex flex-col sm:flex-row sm:items-center gap-3 p-3 rounded-lg border ${cfg.card} hover:border-primary/30 transition-colors`}
              >
                <div className={`w-1 h-12 rounded-full ${cfg.dot} hidden sm:block shrink-0`} />
                <div className="flex-1 min-w-0 space-y-2">
                  <MatchTeamsRow
                    homeTeam={item.home_team || "Home"}
                    awayTeam={item.away_team || "Away"}
                    countryHint={item.country || item.league}
                    size="sm"
                  />
                  <div className="text-xs text-muted-foreground flex flex-wrap gap-x-3 gap-y-1 pl-1">
                    <span>
                      Prediction:{" "}
                      <span className="text-foreground font-medium">{pick1x2Label(predicted)}</span>
                    </span>
                    {confidence != null && (
                      <span className="tabular-nums">
                        {Math.round(Number(confidence))}% confidence
                      </span>
                    )}
                    <span>{formatShortDate(item.evaluated_at || item.match_date || item.viewed_at)}</span>
                  </div>
                </div>
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold shrink-0 ${cfg.badge}`}>
                  <Icon className="w-3.5 h-3.5" />
                  {cfg.label}
                </span>
              </div>
            );

            if (entryId) {
              return (
                <Link key={entryId} to={`/history/${entryId}`} className="block">
                  {inner}
                </Link>
              );
            }
            return <div key={`${item.fixture_id}-${item.match_date}`}>{inner}</div>;
          })}
        </div>
      )}
    </div>
  );
}
