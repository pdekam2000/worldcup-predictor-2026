import React, { useState, useEffect, useCallback } from "react";
import { base44 } from "@/api/base44Client";
import { fetchUpcomingMatches } from "@/api/worldcupApi";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  TrendingUp, Target, Trophy, Activity, ArrowRight, Clock, Calendar,
  AlertCircle, RefreshCw,
} from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { Button } from "@/components/ui/button";

const mockChartData = [
  { month: "Jan", accuracy: 68 }, { month: "Feb", accuracy: 71 }, { month: "Mar", accuracy: 69 },
  { month: "Apr", accuracy: 74 }, { month: "May", accuracy: 72 }, { month: "Jun", accuracy: 76 },
];

const mockRecentPredictions = [
  { home: "Man City", away: "Liverpool", league: "Premier League", prediction: "home", confidence: 72, result: "correct" },
  { home: "Barcelona", away: "Real Madrid", league: "La Liga", prediction: "away", confidence: 58, result: "incorrect" },
  { home: "Bayern", away: "Dortmund", league: "Bundesliga", prediction: "home", confidence: 81, result: "correct" },
  { home: "PSG", away: "Marseille", league: "Ligue 1", prediction: "home", confidence: 77, result: "pending" },
];

export default function Dashboard() {
  const [user, setUser] = useState(null);
  const [matches, setMatches] = useState([]);
  const [matchesLoading, setMatchesLoading] = useState(true);
  const [matchesError, setMatchesError] = useState(null);

  const loadMatches = useCallback(async () => {
    setMatchesLoading(true);
    setMatchesError(null);
    try {
      const result = await fetchUpcomingMatches({ limit: 5 });
      setMatches(result.matches);
    } catch (err) {
      setMatches([]);
      setMatchesError(err instanceof Error ? err.message : "Failed to load matches from API.");
    } finally {
      setMatchesLoading(false);
    }
  }, []);

  useEffect(() => {
    base44.auth.me().then(setUser).catch(() => {});
    loadMatches();
  }, [loadMatches]);

  const stats = [
    { label: "Today's Predictions", value: "12", icon: Target, color: "text-primary", bg: "bg-primary/10" },
    { label: "Win Rate", value: "73.2%", icon: TrendingUp, color: "text-green-400", bg: "bg-green-500/10" },
    { label: "Matches Analyzed", value: "148", icon: Trophy, color: "text-accent", bg: "bg-yellow-500/10" },
    { label: "Streak", value: "5W", icon: Activity, color: "text-purple-400", bg: "bg-purple-500/10" },
  ];

  const matchesEmpty = !matchesLoading && !matchesError && matches.length === 0;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-display font-bold">Welcome back{user?.full_name ? `, ${user.full_name}` : ""}</h1>
        <p className="text-sm text-muted-foreground mt-1">Here's your prediction overview for today.</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className="glass rounded-xl p-4"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-muted-foreground">{s.label}</span>
              <div className={`w-8 h-8 rounded-lg ${s.bg} flex items-center justify-center`}>
                <s.icon className={`w-4 h-4 ${s.color}`} />
              </div>
            </div>
            <div className="text-2xl font-display font-bold">{s.value}</div>
          </motion.div>
        ))}
      </div>

      <div className="grid lg:grid-cols-5 gap-6">
        {/* Performance chart */}
        <div className="lg:col-span-3 glass rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-semibold">Performance Trend</h2>
            <span className="text-xs text-muted-foreground">Last 6 months</span>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={mockChartData}>
              <defs>
                <linearGradient id="blueGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(217, 91%, 60%)" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="hsl(217, 91%, 60%)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="month" tick={{ fill: "hsl(215, 20%, 55%)", fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis domain={[60, 85]} tick={{ fill: "hsl(215, 20%, 55%)", fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: "hsl(222, 47%, 9%)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "12px", fontSize: "12px" }}
                itemStyle={{ color: "hsl(210, 40%, 98%)" }}
                labelStyle={{ color: "hsl(215, 20%, 55%)" }}
              />
              <Area type="monotone" dataKey="accuracy" stroke="hsl(217, 91%, 60%)" fill="url(#blueGrad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Today's top matches */}
        <div className="lg:col-span-2 glass rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-semibold">Today's Matches</h2>
            <Link to="/matches" className="text-primary text-xs font-medium flex items-center gap-1 hover:underline">
              View All <ArrowRight className="w-3 h-3" />
            </Link>
          </div>

          {matchesLoading && (
            <div className="flex items-center justify-center py-10">
              <div className="w-6 h-6 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
            </div>
          )}

          {matchesError && (
            <div className="text-center py-6">
              <AlertCircle className="w-8 h-8 mx-auto mb-2 text-red-400" />
              <p className="text-xs text-red-300 mb-1">Could not load matches from API</p>
              <p className="text-xs text-muted-foreground mb-3">{matchesError}</p>
              <Button type="button" variant="outline" size="sm" className="border-white/10" onClick={loadMatches}>
                <RefreshCw className="w-3.5 h-3.5 mr-2" />
                Retry
              </Button>
            </div>
          )}

          {matchesEmpty && (
            <div className="text-center py-10 text-muted-foreground">
              <Target className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No live backend matches available right now.</p>
            </div>
          )}

          {!matchesLoading && !matchesError && matches.length > 0 && (
            <div className="space-y-3">
              {matches.map((m) => (
                <Link
                  key={m.id}
                  to={`/prediction/${m.id}`}
                  className="flex items-center justify-between p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{m.home_team} vs {m.away_team}</div>
                    <div className="text-xs text-muted-foreground flex items-center gap-2 mt-0.5 flex-wrap">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" /> {m.league}
                      </span>
                      {m.match_date && (
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {new Date(m.match_date).toLocaleDateString([], { month: "short", day: "numeric" })}
                          {" "}
                          {new Date(m.match_date).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-xs px-2 py-1 rounded-full bg-primary/10 text-primary font-medium uppercase ml-2 shrink-0">
                    {m.status || "NS"}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent predictions — no backend endpoint yet */}
      <div className="glass rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display font-semibold">Recent Predictions</h2>
          <Link to="/accuracy" className="text-primary text-xs font-medium flex items-center gap-1 hover:underline">
            View History <ArrowRight className="w-3 h-3" />
          </Link>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground text-xs">
                <th className="pb-3 font-medium">Match</th>
                <th className="pb-3 font-medium">League</th>
                <th className="pb-3 font-medium">Prediction</th>
                <th className="pb-3 font-medium">Confidence</th>
                <th className="pb-3 font-medium">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {mockRecentPredictions.map((p, i) => (
                <tr key={i} className="hover:bg-white/5">
                  <td className="py-3 font-medium">{p.home} vs {p.away}</td>
                  <td className="py-3 text-muted-foreground">{p.league}</td>
                  <td className="py-3">
                    <span className="px-2 py-1 rounded-md text-xs font-medium bg-primary/10 text-primary uppercase">
                      {p.prediction === "home" ? "1" : p.prediction === "draw" ? "X" : "2"}
                    </span>
                  </td>
                  <td className="py-3">{p.confidence}%</td>
                  <td className="py-3">
                    <span className={`px-2 py-1 rounded-md text-xs font-medium ${
                      p.result === "correct" ? "bg-green-500/10 text-green-400" :
                      p.result === "incorrect" ? "bg-red-500/10 text-red-400" :
                      "bg-yellow-500/10 text-yellow-400"
                    }`}>
                      {p.result.charAt(0).toUpperCase() + p.result.slice(1)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
