import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, TrendingUp, CheckCircle, XCircle, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";

const SELECTION_LABELS = { home_win: "HOME", away_win: "AWAY", draw: "DRAW" };
const SELECTION_COLORS = {
  home_win: "bg-blue-500/20 text-blue-400 border border-blue-500/30",
  away_win: "bg-red-500/20 text-red-400 border border-red-500/30",
  draw: "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30",
};

function ResultBadge({ result }) {
  if (!result || result === "pending") return (
    <span className="flex items-center gap-1 text-xs text-slate-400">
      <Clock className="w-3 h-3" /> Pending
    </span>
  );
  if (result === "won") return (
    <span className="flex items-center gap-1 text-xs text-green-400 font-bold">
      <CheckCircle className="w-3 h-3" /> WON
    </span>
  );
  return (
    <span className="flex items-center gap-1 text-xs text-red-400 font-bold">
      <XCircle className="w-3 h-3" /> LOST
    </span>
  );
}

function PickCard({ pick }) {
  const sel = pick.selection || "";
  const selLabel = SELECTION_LABELS[sel] || sel.toUpperCase();
  const selColor = SELECTION_COLORS[sel] || "bg-slate-500/20 text-slate-400";
  const conf = (pick.confidence || 0).toFixed(1);
  const odds = pick.odds || {};
  const selKey = { home_win: "home", away_win: "away", draw: "draw" }[sel] || "";
  const realOdds = odds[selKey];
  const kickoff = pick.kickoff
    ? new Date(pick.kickoff).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
    : "";

  // Kelly stake
  const prob = pick.confidence / 100;
  const b = (realOdds || 0) - 1;
  const kelly = b > 0 ? Math.max(0, ((b * prob - (1 - prob)) / b) * 0.25 * 100) : 0;
  const profit = kelly > 0 && realOdds ? (kelly * (realOdds - 1)).toFixed(2) : null;

  return (
    <div className={`rounded-xl border p-5 transition-all ${
      pick.result === "won" ? "border-green-500/40 bg-green-900/40" :
      pick.result === "lost" ? "border-red-500/40 bg-red-900/40" :
      "border-slate-600 bg-slate-800"
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs bg-slate-700/50 text-slate-400 px-2 py-1 rounded-full">
          {pick.league || "World Cup"}
        </span>
        <div className="flex items-center gap-2">
          {kickoff && <span className="text-xs text-slate-500">{kickoff}</span>}
          <ResultBadge result={pick.result} />
        </div>
      </div>

      {/* Match */}
      <div className="text-base font-semibold text-white mb-3 drop-shadow">
        {pick.home} vs {pick.away}
      </div>

      {/* Pick + Confidence */}
      <div className="flex items-center gap-2 mb-4">
        <span className={`text-xs font-bold px-3 py-1 rounded-full ${selColor}`}>
          {selLabel}
        </span>
        <span className="text-xs bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 px-3 py-1 rounded-full">
          {conf}% conf
        </span>
      </div>

      {/* Odds + Kelly */}
      <div className="flex items-center justify-between pt-3 border-t border-slate-700/50">
        <div>
          <div className="text-xs text-slate-500 mb-1">Odds</div>
          <div className="text-xl font-bold text-yellow-400">
            {realOdds ? realOdds.toFixed(2) : "N/A"}
          </div>
        </div>
        {kelly > 0 && (
          <div className="text-right">
            <div className="text-xs text-slate-500 mb-1">Kelly Stake</div>
            <div className="text-sm font-semibold text-white">€{kelly.toFixed(2)}</div>
            {profit && <div className="text-xs text-green-400">+€{profit} potential</div>}
          </div>
        )}
      </div>
    </div>
  );
}

function StatsBar({ picks }) {
  const won = picks.filter(p => p.result === "won").length;
  const lost = picks.filter(p => p.result === "lost").length;
  const total = won + lost;
  const winRate = total > 0 ? (won / total * 100).toFixed(0) : null;
  const avgConf = picks.length > 0
    ? (picks.reduce((s, p) => s + (p.confidence || 0), 0) / picks.length).toFixed(0)
    : null;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
      {[
        { label: "Today's Picks", value: picks.length, color: "text-indigo-400" },
        { label: "Avg Confidence", value: avgConf ? `${avgConf}%` : "—", color: "text-indigo-400" },
        { label: "Win Rate", value: winRate ? `${winRate}%` : "—", color: "text-green-400" },
        { label: "Record", value: total > 0 ? `${won}W / ${lost}L` : "—", color: "text-white" },
      ].map(s => (
        <div key={s.label} className="bg-slate-800 border border-slate-700 rounded-xl p-4">
          <div className="text-xs text-slate-400 mb-1">{s.label}</div>
          <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
        </div>
      ))}
    </div>
  );
}

export default function DailyPicksPage() {
  const [picks, setPicks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // try API endpoint first
      const res = await fetch(`/api/daily-picks?date=${date}`);
      if (res.ok) {
        const data = await res.json();
        setPicks(data.picks || []);
        return;
      }
      throw new Error("No picks available for today.");
    } catch (e) {
      setError(e.message);
      setPicks([]);
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => { load(); }, [load]);

  const today = new Date().toLocaleDateString("en-GB", {
    weekday: "long", day: "numeric", month: "long", year: "numeric"
  });

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 bg-slate-900 min-h-screen">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-indigo-400" />
            Daily Picks
          </h1>
          <p className="text-sm text-slate-400 mt-1">{today}</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Stats */}
      <StatsBar picks={picks} />

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400 mb-4">
          {error}
          <div className="text-xs text-slate-500 mt-1">
            Run: <code>python scripts/daily_picks.py</code>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="text-center py-12 text-slate-400 text-sm">Loading picks...</div>
      )}

      {/* No picks */}
      {!loading && !error && picks.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-700 p-10 text-center">
          <p className="text-slate-400 text-sm">No confident picks today.</p>
          <p className="text-slate-500 text-xs mt-2">Check back after running the daily picks script.</p>
        </div>
      )}

      {/* Picks */}
      <div className="space-y-4">
        {picks.map((pick, i) => (
          <PickCard key={`${pick.fixture_id}-${i}`} pick={pick} />
        ))}
      </div>
    </div>
  );
}
