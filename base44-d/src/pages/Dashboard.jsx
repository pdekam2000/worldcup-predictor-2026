import React, { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/lib/AuthContext";
import { fetchDashboard, fetchGoalTimingPicks, fetchGoalTimingAccuracy } from "@/api/saasApi";
import { fetchUpcomingMatches, fetchMatches } from "@/api/worldcupApi";
import { fetchSubscription } from "@/api/saasApi";
import {
  TrendingUp, Target, Trophy, Activity, Crown, Zap, Radio, Calendar,
  AlertCircle, RefreshCw, Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  SectionHeader,
  WinrateCard,
  PredictionCard,
  TerminalCard,
  LivePulse,
} from "@/components/terminal";

function isLiveMatch(m) {
  const s = String(m.status || m.bucket || "").toLowerCase();
  return ["live", "1h", "2h", "ht"].includes(s);
}

function isWorldCup(league) {
  const l = String(league || "").toLowerCase();
  return l.includes("world cup") || l.includes("world_cup") || l.includes("wc ");
}

export default function Dashboard() {
  const { user } = useAuth();
  const [matches, setMatches] = useState([]);
  const [liveMatches, setLiveMatches] = useState([]);
  const [matchesLoading, setMatchesLoading] = useState(true);
  const [matchesError, setMatchesError] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState(null);
  const [bestPick, setBestPick] = useState(null);
  const [accuracy, setAccuracy] = useState(null);
  const [subscription, setSubscription] = useState(null);

  const loadMatches = useCallback(async () => {
    setMatchesLoading(true);
    setMatchesError(null);
    try {
      const [upcoming, live] = await Promise.all([
        fetchUpcomingMatches({ limit: 8 }),
        fetchMatches({ status: "live", page_size: 6 }).catch(() => ({ matches: [] })),
      ]);
      setMatches(upcoming.matches || []);
      setLiveMatches(live.matches || []);
    } catch (err) {
      setMatches([]);
      setLiveMatches([]);
      setMatchesError(err instanceof Error ? err.message : "Failed to load matches.");
    } finally {
      setMatchesLoading(false);
    }
  }, []);

  const loadDashboard = useCallback(async () => {
    setDashboardLoading(true);
    setDashboardError(null);
    try {
      const [dash, picks, acc, sub] = await Promise.all([
        fetchDashboard(),
        fetchGoalTimingPicks({ limit: 1 }).catch(() => null),
        fetchGoalTimingAccuracy().catch(() => null),
        fetchSubscription().catch(() => null),
      ]);
      setDashboard(dash);
      setBestPick(picks?.picks?.[0] || null);
      setAccuracy(acc);
      setSubscription(sub?.subscription || sub);
    } catch (err) {
      setDashboard(null);
      setDashboardError(err instanceof Error ? err.message : "Failed to load dashboard.");
    } finally {
      setDashboardLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMatches();
    loadDashboard();
  }, [loadMatches, loadDashboard]);

  const statsData = dashboard?.stats;
  const bestMarket = useMemo(() => {
    const markets = accuracy?.markets || accuracy?.accuracy_by_market || [];
    if (!Array.isArray(markets) || !markets.length) return null;
    const sorted = [...markets].sort((a, b) => (b.accuracy || b.winrate_pct || 0) - (a.accuracy || a.winrate_pct || 0));
    return sorted[0];
  }, [accuracy]);

  const planLabel = subscription?.plan_name || subscription?.plan || "Free";
  const planStatus = subscription?.status || "active";

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="terminal-section-title mb-2">Intelligence terminal</p>
          <h1 className="text-2xl sm:text-3xl font-display font-bold text-[#F8FAFC]">
            {user?.full_name ? `Welcome, ${user.full_name.split(" ")[0]}` : "Command Center"}
          </h1>
          <p className="text-sm text-[#94A3B8] mt-1 max-w-xl">
            Your best picks, live fixtures, and model trust — at a glance.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <LivePulse className="sm:hidden" />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => { loadMatches(); loadDashboard(); }}
            className="border-white/10 bg-[#101827] text-[#F8FAFC] hover:bg-white/5"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${dashboardLoading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {dashboardError && (
        <TerminalCard className="border-[#FF4D4D]/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <span className="text-sm text-[#FF4D4D]">{dashboardError}</span>
          <Button type="button" variant="outline" size="sm" onClick={loadDashboard}>Retry</Button>
        </TerminalCard>
      )}

      {/* Hero: Today's Best Pick */}
      <section>
        <SectionHeader eyebrow="Signal" title="Today's Best Pick" actionLabel="All picks" actionTo="/goal-timing/picks" />
        <div className="mt-4">
          {dashboardLoading ? (
            <TerminalCard className="h-48 flex items-center justify-center">
              <div className="w-8 h-8 border-2 border-[#00E676]/20 border-t-[#00E676] rounded-full animate-spin" />
            </TerminalCard>
          ) : bestPick ? (
            <PredictionCard pick={bestPick} match={bestPick} variant="goal_timing" featured />
          ) : (
            <TerminalCard glow>
              <p className="text-[#94A3B8] text-sm">No EGIE pick published yet today.</p>
              <Link to="/goal-timing/picks" className="text-[#00E676] text-sm font-medium mt-2 inline-block">
                Check goal timing picks →
              </Link>
            </TerminalCard>
          )}
        </div>
      </section>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <WinrateCard
          label="Model Winrate"
          value={statsData?.settled ? `${statsData.win_rate}%` : accuracy?.overall_winrate_pct != null ? `${accuracy.overall_winrate_pct}%` : "—"}
          sub="Settled predictions"
          icon={TrendingUp}
          accent="green"
          loading={dashboardLoading}
        />
        <WinrateCard
          label="Best Market Today"
          value={bestMarket ? (bestMarket.market_name || bestMarket.market || "—") : "—"}
          sub={bestMarket?.accuracy != null ? `${Math.round(bestMarket.accuracy * (bestMarket.accuracy <= 1 ? 100 : 1))}% hit rate` : "From accuracy API"}
          icon={Sparkles}
          accent="gold"
          loading={dashboardLoading}
        />
        <WinrateCard
          label="Matches Analyzed"
          value={String(statsData?.matches_analyzed ?? "—")}
          icon={Trophy}
          accent="blue"
          loading={dashboardLoading}
        />
        <WinrateCard
          label="Subscription"
          value={planLabel}
          sub={planStatus}
          icon={Crown}
          accent={planLabel.toLowerCase() === "free" ? "neutral" : "gold"}
          loading={dashboardLoading}
        />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Live */}
        <section>
          <SectionHeader
            eyebrow="Now"
            title="Live Matches"
            actionLabel="Match center"
            actionTo="/matches?status=live"
          />
          <div className="mt-4 space-y-3">
            {matchesLoading ? (
              <TerminalCard className="py-12 flex justify-center">
                <div className="w-6 h-6 border-2 border-[#00E676]/20 border-t-[#00E676] rounded-full animate-spin" />
              </TerminalCard>
            ) : liveMatches.length > 0 ? (
              liveMatches.slice(0, 4).map((m) => (
                <PredictionCard key={m.id} match={m} variant="match" />
              ))
            ) : matches.filter(isLiveMatch).length > 0 ? (
              matches.filter(isLiveMatch).slice(0, 4).map((m) => (
                <PredictionCard key={m.id} match={m} variant="match" />
              ))
            ) : (
              <TerminalCard>
                <Radio className="w-8 h-8 text-[#94A3B8] mb-2 opacity-50" />
                <p className="text-sm text-[#94A3B8]">No live fixtures right now.</p>
              </TerminalCard>
            )}
          </div>
        </section>

        {/* Upcoming */}
        <section>
          <SectionHeader eyebrow="Next" title="Upcoming Picks" actionLabel="View all" actionTo="/matches" />
          <div className="mt-4 space-y-3">
            {matchesError && (
              <TerminalCard className="text-center text-sm text-[#FF4D4D]">{matchesError}</TerminalCard>
            )}
            {!matchesLoading && !matchesError && matches.length === 0 && (
              <TerminalCard className="text-center text-sm text-[#94A3B8]">No upcoming matches.</TerminalCard>
            )}
            {!matchesLoading &&
              matches
                .filter((m) => !isLiveMatch(m))
                .slice(0, 4)
                .map((m) => (
                  <PredictionCard key={m.id} match={m} variant="match" />
                ))}
          </div>
        </section>
      </div>

      {/* Quick hubs */}
      <div className="grid sm:grid-cols-2 gap-4">
        <Link to="/matches?hub=worldcup" className="terminal-card-glow p-5 block hover:border-[#FFD166]/30 transition-colors group">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-2xl">🏆</span>
            <h3 className="font-display font-bold text-[#F8FAFC]">World Cup Center</h3>
          </div>
          <p className="text-sm text-[#94A3B8]">Groups, flags, fixtures & WC predictions</p>
          <span className="text-[#00E676] text-sm font-medium mt-3 inline-flex items-center gap-1 group-hover:gap-2 transition-all">
            Enter <Zap className="w-3.5 h-3.5" />
          </span>
        </Link>
        <Link to="/matches?hub=leagues" className="terminal-card p-5 block hover:border-[#3B82F6]/30 transition-colors group">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-2xl">⚽</span>
            <h3 className="font-display font-bold text-[#F8FAFC]">League Center</h3>
          </div>
          <p className="text-sm text-[#94A3B8]">Premier League, La Liga & club competitions</p>
          <span className="text-[#3B82F6] text-sm font-medium mt-3 inline-flex items-center gap-1 group-hover:gap-2 transition-all">
            Browse leagues <Activity className="w-3.5 h-3.5" />
          </span>
        </Link>
      </div>

      {/* Recent activity */}
      {(dashboard?.recent_predictions?.length > 0) && (
        <section>
          <SectionHeader title="Recent Activity" actionLabel="Full history" actionTo="/history" />
          <TerminalCard className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[#94A3B8] text-xs border-b border-white/[0.06]">
                  <th className="pb-3 font-medium">Match</th>
                  <th className="pb-3 font-medium">Pick</th>
                  <th className="pb-3 font-medium">Result</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {dashboard.recent_predictions.slice(0, 5).map((p) => (
                  <tr key={p.id} className="hover:bg-white/[0.02]">
                    <td className="py-3 font-medium text-[#F8FAFC]">{p.home_team} vs {p.away_team}</td>
                    <td className="py-3">
                      <span className="terminal-chip border-[#00E676]/30 bg-[#00E676]/10 text-[#00E676]">
                        {p.prediction_1x2 === "home" ? "1" : p.prediction_1x2 === "draw" ? "X" : "2"}
                      </span>
                    </td>
                    <td className="py-3">
                      <span className={`terminal-chip ${
                        p.result === "correct" ? "border-[#00E676]/40 bg-[#00E676]/10 text-[#00E676]" :
                        p.result === "incorrect" ? "border-[#FF4D4D]/40 bg-[#FF4D4D]/10 text-[#FF4D4D]" :
                        "border-[#FFD166]/40 bg-[#FFD166]/10 text-[#FFD166]"
                      }`}>
                        {p.result || "Pending"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TerminalCard>
        </section>
      )}
    </div>
  );
}
