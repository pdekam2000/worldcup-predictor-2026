import React, { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Search, Calendar, ChevronRight, Trophy, Clock, Target, AlertCircle, RefreshCw } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { fetchUpcomingMatches } from "@/api/worldcupApi";

function getConfidenceColor(c) {
  if (c >= 75) return "text-green-400 bg-green-500/10";
  if (c >= 60) return "text-primary bg-primary/10";
  return "text-yellow-400 bg-yellow-500/10";
}

export default function MatchCenter() {
  const [matches, setMatches] = useState([]);
  const [search, setSearch] = useState("");
  const [leagueFilter, setLeagueFilter] = useState("All Leagues");
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(null);

  const loadMatches = useCallback(async () => {
    setLoading(true);
    setApiError(null);
    try {
      const result = await fetchUpcomingMatches({ limit: 50 });
      setMatches(result.matches);
    } catch (err) {
      setMatches([]);
      setApiError(err instanceof Error ? err.message : "Failed to load matches from API.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMatches();
  }, [loadMatches]);

  const leagueOptions = [
    "All Leagues",
    ...Array.from(new Set(matches.map((m) => m.league).filter(Boolean))).sort(),
  ];

  const filtered = matches.filter((m) => {
    const matchSearch = `${m.home_team} ${m.away_team} ${m.league}`.toLowerCase().includes(search.toLowerCase());
    const matchLeague = leagueFilter === "All Leagues" || m.league === leagueFilter;
    return matchSearch && matchLeague;
  });

  const backendEmpty = !loading && !apiError && matches.length === 0;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-display font-bold">Match Center</h1>
        <p className="text-sm text-muted-foreground mt-1">Browse upcoming fixtures — open a match to run prediction on demand.</p>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search teams or leagues..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10 bg-white/5 border-white/10 rounded-xl"
            disabled={loading || !!apiError}
          />
        </div>
        <Select value={leagueFilter} onValueChange={setLeagueFilter} disabled={loading || !!apiError}>
          <SelectTrigger className="w-full sm:w-48 bg-white/5 border-white/10 rounded-xl">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-card border-white/10">
            {leagueOptions.map((l) => (
              <SelectItem key={l} value={l}>
                {l}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {apiError && (
        <div className="glass rounded-xl p-6 text-center border border-red-500/20">
          <AlertCircle className="w-10 h-10 mx-auto mb-3 text-red-400" />
          <p className="text-sm font-medium text-red-300 mb-1">Could not load matches from API</p>
          <p className="text-xs text-muted-foreground mb-4 max-w-md mx-auto">{apiError}</p>
          <Button type="button" variant="outline" size="sm" className="border-white/10" onClick={loadMatches}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Retry
          </Button>
        </div>
      )}

      {backendEmpty && (
        <div className="text-center py-16 text-muted-foreground glass rounded-xl">
          <Target className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>No upcoming matches available from backend right now.</p>
        </div>
      )}

      {/* Match cards */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
        </div>
      ) : (
        !apiError &&
        matches.length > 0 && (
          <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {filtered.map((m, i) => (
              <motion.div
                key={m.id || i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
              >
                <Link to={`/prediction/${m.id}`} className="block glass rounded-xl p-5 hover:bg-white/10 transition-all group">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Trophy className="w-3.5 h-3.5" />
                      {m.league}
                    </div>
                    {m.confidence != null ? (
                      <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${getConfidenceColor(m.confidence)}`}>
                        {m.confidence}%
                      </span>
                    ) : (
                      <span className="px-2.5 py-1 rounded-full text-xs font-semibold text-muted-foreground bg-white/5 uppercase">
                        {m.status || "NS"}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center justify-between mb-4">
                    <div className="flex-1 text-center">
                      <div className="w-12 h-12 mx-auto rounded-xl bg-white/5 flex items-center justify-center mb-2 text-lg font-bold text-primary">
                        {m.home_team?.slice(0, 2).toUpperCase()}
                      </div>
                      <div className="text-sm font-medium truncate">{m.home_team}</div>
                    </div>
                    <div className="px-4 text-center">
                      <div className="text-xs text-muted-foreground mb-1">VS</div>
                      {m.prediction ? (
                        <div className="text-xs font-semibold px-2 py-0.5 rounded bg-primary/10 text-primary uppercase">
                          {m.prediction === "home" ? "1" : m.prediction === "draw" ? "X" : "2"}
                        </div>
                      ) : (
                        <div className="text-xs text-muted-foreground">—</div>
                      )}
                    </div>
                    <div className="flex-1 text-center">
                      <div className="w-12 h-12 mx-auto rounded-xl bg-white/5 flex items-center justify-center mb-2 text-lg font-bold text-accent">
                        {m.away_team?.slice(0, 2).toUpperCase()}
                      </div>
                      <div className="text-sm font-medium truncate">{m.away_team}</div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {m.match_date ? new Date(m.match_date).toLocaleDateString() : "—"}
                    </div>
                    <div className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {m.match_date
                        ? new Date(m.match_date).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                        : "—"}
                    </div>
                    <ChevronRight className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity text-primary" />
                  </div>
                </Link>
              </motion.div>
            ))}
          </div>
        )
      )}

      {!loading && !apiError && matches.length > 0 && filtered.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <Target className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>No matches found.</p>
        </div>
      )}
    </div>
  );
}
