import React, { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight, Calendar, Radio, CheckCircle2, Clock, AlertCircle, RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import MatchTeamsRow from "@/components/match/MatchTeamsRow";

const TABS = [
  { id: "upcoming", label: "Upcoming", icon: Calendar },
  { id: "live", label: "Live", icon: Radio },
  { id: "finished", label: "Finished", icon: CheckCircle2 },
];

const EMPTY_COPY = {
  upcoming: "No upcoming matches scheduled in the backend right now.",
  live: "No live matches at the moment.",
  finished: "No recently finished matches available.",
};

export default function MatchPreviewPanel({ matchesByStatus, loading, error, onRetry }) {
  const [tab, setTab] = useState("upcoming");
  const matches = matchesByStatus?.[tab] || [];
  const TabIcon = TABS.find((t) => t.id === tab)?.icon || Calendar;

  return (
    <div className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="font-display font-semibold">Match Center</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Quick preview by match status</p>
        </div>
        <Link
          to={`/matches?status=${tab}`}
          className="text-primary text-xs font-medium flex items-center gap-1 hover:underline"
        >
          Open Match Center <ArrowRight className="w-3 h-3" />
        </Link>
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        {TABS.map((t) => {
          const Icon = t.icon;
          const count = matchesByStatus?.[t.id]?.length ?? 0;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                tab === t.id
                  ? "bg-primary/15 text-primary border-primary/30"
                  : "border-border text-muted-foreground hover:text-foreground hover:bg-muted/60"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {t.label}
              {!loading && count > 0 && (
                <span className="ml-0.5 px-1.5 py-0.5 rounded-full bg-muted text-[10px] tabular-nums">
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {loading && (
        <div className="flex justify-center py-10">
          <div className="w-6 h-6 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
        </div>
      )}

      {error && !loading && (
        <div className="text-center py-8">
          <AlertCircle className="w-8 h-8 mx-auto mb-2 text-red-400" />
          <p className="text-xs text-red-600 mb-3">{error}</p>
          <Button type="button" variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw className="w-3.5 h-3.5 mr-2" /> Retry
          </Button>
        </div>
      )}

      {!loading && !error && matches.length === 0 && (
        <div className="rounded-lg border border-dashed border-border bg-muted/30 px-4 py-10 text-center">
          <TabIcon className="w-8 h-8 mx-auto mb-3 text-muted-foreground/50" />
          <p className="text-sm text-muted-foreground">{EMPTY_COPY[tab]}</p>
        </div>
      )}

      {!loading && !error && matches.length > 0 && (
        <div className="grid sm:grid-cols-2 gap-3">
          {matches.map((m) => (
            <Link
              key={m.id}
              to={`/prediction/${m.id}`}
              className="block p-3 rounded-lg border border-border bg-card hover:shadow-md hover:border-primary/30 transition-all"
            >
              <MatchTeamsRow
                homeTeam={m.home_team}
                awayTeam={m.away_team}
                homeLogo={m.home_team_logo}
                awayLogo={m.away_team_logo}
                countryHint={m.country}
                size="sm"
                className="mb-2"
              />
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs text-muted-foreground flex items-center gap-2 flex-wrap min-w-0">
                  <span className="truncate">{m.league || "—"}</span>
                  {m.match_date && (
                    <span className="inline-flex items-center gap-1 shrink-0">
                      <Clock className="w-3 h-3" />
                      {new Date(m.match_date).toLocaleDateString([], { month: "short", day: "numeric" })}
                    </span>
                  )}
                </div>
                <span className="text-[10px] px-2 py-1 rounded-full bg-primary/10 text-primary font-semibold uppercase shrink-0">
                  {m.status || tab}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
