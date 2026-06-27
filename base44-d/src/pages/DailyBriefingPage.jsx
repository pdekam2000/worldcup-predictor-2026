import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  BarChart3,
  Calendar,
  NotebookPen,
  RefreshCw,
  Sparkles,
  Ticket,
  TrendingUp,
} from "lucide-react";
import { fetchDailyBriefing, fetchWeeklyInsights } from "@/api/assistantApi";
import { useAuth } from "@/lib/AuthContext";
import { Button } from "@/components/ui/button";
import { SectionHeader, TerminalCard } from "@/components/terminal";

const DISCLAIMER =
  "AI briefing is for analysis and education only. It does not guarantee real-money results.";

export default function DailyBriefingPage() {
  const { isAuthenticated } = useAuth();
  const [briefing, setBriefing] = useState(null);
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [b, w] = await Promise.all([
        fetchDailyBriefing(),
        fetchWeeklyInsights().catch(() => null),
      ]);
      setBriefing(b.briefing);
      setInsights(w?.insights);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load briefing");
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    load();
  }, [load]);

  if (!isAuthenticated) {
    return (
      <div className="max-w-2xl mx-auto text-center py-16">
        <Calendar className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
        <p className="text-muted-foreground">Log in to view your daily AI briefing.</p>
        <Link to="/login" className="text-primary hover:underline mt-2 inline-block">Sign in</Link>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  const b = briefing || {};

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <SectionHeader
        title="Daily AI Briefing"
        subtitle={b.headline || `Summary for ${b.date || "today"}`}
        icon={Sparkles}
      />

      <p className="text-xs text-muted-foreground flex items-start gap-2 glass rounded-lg p-3">
        <AlertTriangle className="w-4 h-4 shrink-0 text-yellow-500" />
        {DISCLAIMER}
      </p>

      {error && <div className="glass rounded-xl p-3 text-sm text-red-300">{error}</div>}

      <div className="grid gap-4 md:grid-cols-2">
        <TerminalCard title="Best singles today">
          {(b.best_singles || []).length === 0 ? (
            <p className="text-sm text-muted-foreground">No singles match your watchlist / quality filters.</p>
          ) : (
            <ul className="space-y-2">
              {b.best_singles.map((leg, i) => (
                <li key={i} className="text-sm glass rounded-lg px-3 py-2">
                  <Link to={`/matches/${leg.fixture_id}`} className="hover:text-primary font-medium">
                    {leg.home_team} vs {leg.away_team}
                  </Link>
                  <p className="text-xs text-muted-foreground">
                    {leg.market} · Q{leg.bet_quality_score ?? "—"}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </TerminalCard>

        <TerminalCard title="Best combos">
          {(b.best_combos || []).length === 0 ? (
            <p className="text-sm text-muted-foreground">No combos available today.</p>
          ) : (
            <ul className="space-y-2">
              {b.best_combos.map((combo, i) => (
                <li key={i} className="text-sm glass rounded-lg px-3 py-2">
                  <p className="font-medium capitalize">{combo.combo_type || combo.type || "Combo"}</p>
                  <p className="text-xs text-muted-foreground">{(combo.legs || []).length} legs</p>
                </li>
              ))}
            </ul>
          )}
          <Link to="/combo-tips" className="text-xs text-primary hover:underline mt-2 inline-block">
            Open Combo Tips
          </Link>
        </TerminalCard>

        <TerminalCard title="Matches to avoid">
          {(b.matches_to_avoid || []).length === 0 ? (
            <p className="text-sm text-muted-foreground">No avoid picks for watched items.</p>
          ) : (
            <ul className="space-y-1 text-sm text-muted-foreground">
              {b.matches_to_avoid.map((leg, i) => (
                <li key={i}>{leg.home_team} vs {leg.away_team}</li>
              ))}
            </ul>
          )}
        </TerminalCard>

        <TerminalCard title="Highest quality fixtures">
          <ul className="space-y-2">
            {(b.highest_quality_fixtures || []).map((leg, i) => (
              <li key={i} className="text-sm flex justify-between glass rounded-lg px-3 py-2">
                <span>{leg.home_team} vs {leg.away_team}</span>
                <span className="text-primary font-mono">Q{leg.bet_quality_score}</span>
              </li>
            ))}
          </ul>
        </TerminalCard>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <TerminalCard title="Paper betting">
          <div className="text-sm space-y-1">
            <p>P/L: <span className="font-mono">{(b.paper_betting?.profit_loss ?? 0).toFixed?.(2) ?? b.paper_betting?.profit_loss}</span></p>
            <p>ROI: {b.paper_betting?.roi_pct ?? "—"}%</p>
            <p>Win rate: {b.paper_betting?.winrate ?? "—"}%</p>
          </div>
          <Link to="/paper-betting" className="text-xs text-primary hover:underline mt-2 inline-flex items-center gap-1">
            <NotebookPen className="w-3 h-3" /> Paper Betting
          </Link>
        </TerminalCard>

        <TerminalCard title="Archive accuracy">
          {b.archive_accuracy?.available ? (
            <p className="text-sm">
              <BarChart3 className="w-4 h-4 inline mr-1 text-green-400" />
              {b.archive_accuracy.accuracy_pct}% over {b.archive_accuracy.settled} settled picks
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">No archive data yet.</p>
          )}
          <Link to="/archive" className="text-xs text-primary hover:underline mt-2 inline-block">Archive</Link>
        </TerminalCard>

        <TerminalCard title="Weekly insights">
          {insights?.available ? (
            <div className="text-sm space-y-1">
              <p>Win rate: {insights.winrate_trend}%</p>
              <p>Best market: {insights.best_market || "—"}</p>
              <p>Avg quality: {insights.average_quality ?? "—"}</p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{insights?.message || "Need more settled bets."}</p>
          )}
        </TerminalCard>
      </div>

      {(b.quality_changes_overnight || []).length > 0 && (
        <TerminalCard title="Quality changes overnight">
          <ul className="space-y-2 text-sm">
            {b.quality_changes_overnight.map((n) => (
              <li key={n.id} className="glass rounded-lg px-3 py-2">{n.title}: {n.message}</li>
            ))}
          </ul>
        </TerminalCard>
      )}

      <Button variant="outline" size="sm" onClick={load}>
        <RefreshCw className="w-4 h-4 mr-1" /> Refresh briefing
      </Button>
    </div>
  );
}
