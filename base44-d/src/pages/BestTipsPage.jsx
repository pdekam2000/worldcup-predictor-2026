import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, RefreshCw, Target, Sparkles } from "lucide-react";
import { fetchBestTips } from "@/api/saasApi";
import { formatPercent } from "@/lib/formatPercent";
import { useAuth } from "@/lib/AuthContext";
import { Button } from "@/components/ui/button";
import SaasPageHeader, { SaasCard } from "@/components/saas/SaasPageHeader";

const COMPETITIONS = [
  { key: "world_cup_2026", label: "World Cup 2026" },
  { key: "champions_league", label: "Champions League" },
  { key: "europa_league", label: "Europa League" },
  { key: "conference_league", label: "Conference League" },
  { key: "premier_league", label: "Premier League" },
  { key: "all", label: "All (WC default)" },
];

const MARKET_FILTERS = ["all", "1X2", "BTTS", "Over/Under 2.5", "Double Chance", "First Goal Team"];

const TIER_FILTERS = [
  { key: "all", label: "All tiers" },
  { key: "high", label: "High confidence (≥70%)" },
];

const KICKOFF_FILTERS = [
  { key: "all", label: "Any time" },
  { key: "today", label: "Today" },
  { key: "tomorrow", label: "Tomorrow" },
  { key: "week", label: "This week" },
];

function riskLabel(level) {
  const map = {
    moderate: { text: "Moderate", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
    elevated: { text: "Elevated", className: "bg-amber-50 text-amber-700 border-amber-200" },
    high: { text: "Higher risk", className: "bg-red-50 text-red-700 border-red-200" },
    low_sample: { text: "Low sample", className: "bg-slate-100 text-slate-600 border-slate-200" },
  };
  return map[level] || { text: level || "—", className: "bg-slate-100 text-slate-600 border-slate-200" };
}

function tierFromConfidence(confidence) {
  const c = Number(confidence);
  if (Number.isNaN(c)) return "—";
  if (c >= 75) return "Strong";
  if (c >= 65) return "Solid";
  if (c >= 55) return "Lean";
  return "Caution";
}

function kickoffBucket(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startTomorrow = new Date(startToday);
  startTomorrow.setDate(startTomorrow.getDate() + 1);
  const endTomorrow = new Date(startTomorrow);
  endTomorrow.setDate(endTomorrow.getDate() + 1);
  const endWeek = new Date(startToday);
  endWeek.setDate(endWeek.getDate() + 7);
  if (d >= startToday && d < startTomorrow) return "today";
  if (d >= startTomorrow && d < endTomorrow) return "tomorrow";
  if (d >= startToday && d < endWeek) return "week";
  return "later";
}

function formatKickoff(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function BestTipsPage() {
  const { user } = useAuth();
  const isSuperAdmin = user?.role === "super_admin";

  const [competition, setCompetition] = useState("world_cup_2026");
  const [marketFilter, setMarketFilter] = useState("all");
  const [tierFilter, setTierFilter] = useState("all");
  const [kickoffFilter, setKickoffFilter] = useState("all");
  const [highOnly, setHighOnly] = useState(false);
  const [tips, setTips] = useState([]);
  const [disclaimer, setDisclaimer] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const comp = competition === "all" ? "world_cup_2026" : competition;
      const res = await fetchBestTips({ competition: comp, limit: 40 });
      setTips(res.tips || []);
      setDisclaimer(res.disclaimer || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load best tips");
      setTips([]);
    } finally {
      setLoading(false);
    }
  }, [competition]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    return tips.filter((tip) => {
      if (marketFilter !== "all" && tip.market !== marketFilter) return false;
      const conf = Number(tip.confidence);
      if (tierFilter === "high" && (Number.isNaN(conf) || conf < 70)) return false;
      if (highOnly && (Number.isNaN(conf) || conf < 70)) return false;
      if (kickoffFilter !== "all") {
        const bucket = kickoffBucket(tip.match_date);
        if (bucket !== kickoffFilter) return false;
      }
      return true;
    });
  }, [tips, marketFilter, tierFilter, kickoffFilter, highOnly]);

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-24">
      <SaasPageHeader
        eyebrow="Production picks"
        title="Best Tips"
        subtitle="Strongest model recommendations across upcoming fixtures. Research and analysis only — not betting advice."
        actions={
          <Button variant="outline" size="sm" onClick={load} disabled={loading} className="border-slate-200">
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
        }
      />

      <SaasCard className="p-4 border-amber-200 bg-amber-50/80">
        <p className="text-sm text-amber-900 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>
            Probability = chance of outcome. Confidence = model trust. Tier = recommendation strength.
            Combined bets carry higher risk — never guaranteed profit.
          </span>
        </p>
      </SaasCard>

      <div className="flex flex-wrap gap-2">
        {COMPETITIONS.map((c) => (
          <button
            key={c.key}
            type="button"
            onClick={() => setCompetition(c.key)}
            className={`text-xs px-3 py-1.5 rounded-full border font-medium transition-colors ${
              competition === c.key
                ? "bg-amber-500 text-white border-amber-500"
                : "bg-white text-slate-600 border-slate-200 hover:border-amber-300"
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-3 items-center text-sm">
        <label className="text-slate-500">
          Market{" "}
          <select
            value={marketFilter}
            onChange={(e) => setMarketFilter(e.target.value)}
            className="ml-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-slate-800"
          >
            {MARKET_FILTERS.map((m) => (
              <option key={m} value={m}>{m === "all" ? "All markets" : m}</option>
            ))}
          </select>
        </label>
        <label className="text-slate-500">
          Tier{" "}
          <select
            value={tierFilter}
            onChange={(e) => setTierFilter(e.target.value)}
            className="ml-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-slate-800"
          >
            {TIER_FILTERS.map((t) => (
              <option key={t.key} value={t.key}>{t.label}</option>
            ))}
          </select>
        </label>
        <label className="text-slate-500">
          Kickoff{" "}
          <select
            value={kickoffFilter}
            onChange={(e) => setKickoffFilter(e.target.value)}
            className="ml-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-slate-800"
          >
            {KICKOFF_FILTERS.map((k) => (
              <option key={k.key} value={k.key}>{k.label}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-slate-600 cursor-pointer">
          <input type="checkbox" checked={highOnly} onChange={(e) => setHighOnly(e.target.checked)} className="rounded" />
          High confidence only
        </label>
      </div>

      {error && (
        <SaasCard className="p-4 text-red-600 border-red-200 bg-red-50">{error}</SaasCard>
      )}

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-2 border-amber-200 border-t-amber-500 rounded-full animate-spin" />
        </div>
      ) : filtered.length === 0 && tips.length === 0 ? (
        <SaasCard className="p-12 text-center text-slate-500">
          <Target className="w-10 h-10 mx-auto mb-3 text-slate-300" />
          <p className="font-medium text-slate-700 mb-1">No program best bets right now</p>
          <p className="text-sm max-w-md mx-auto">
            The model has not flagged strong edges for this competition yet. Try Match Center to run per-fixture analysis, or check back closer to kickoff.
          </p>
          <Link to="/matches" className="inline-block mt-4 text-sm font-medium text-amber-600 hover:text-amber-700">
            Open Match Center →
          </Link>
        </SaasCard>
      ) : filtered.length === 0 ? (
        <SaasCard className="p-12 text-center text-slate-500">
          <Target className="w-10 h-10 mx-auto mb-3 text-slate-300" />
          No tips match your filters. Try another competition or loosen filters.
        </SaasCard>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {filtered.map((tip) => {
            const risk = riskLabel(tip.risk_level);
            const tier = tierFromConfidence(tip.confidence);
            const fixtureId = tip.fixture_id;
            return (
              <SaasCard key={`${tip.fixture_id}-${tip.market_key}`} className="p-5 hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between gap-2 mb-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-amber-600">{tip.market}</p>
                    <h2 className="text-lg font-bold text-slate-900 mt-0.5">{tip.match_name}</h2>
                    <p className="text-xs text-slate-500 mt-1">{formatKickoff(tip.match_date)}</p>
                  </div>
                  <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-full bg-slate-900 text-amber-400">
                    <Sparkles className="w-3 h-3" /> Classic
                  </span>
                </div>

                <p className="text-xl font-semibold text-slate-900 mb-3">{tip.prediction}</p>

                <div className="flex flex-wrap gap-2 mb-3">
                  <span className="text-xs px-2 py-1 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                    Confidence {formatPercent(tip.confidence, { digits: 0 })}
                  </span>
                  <span className="text-xs px-2 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                    Tier {tier}
                  </span>
                  <span className={`text-xs px-2 py-1 rounded-full border ${risk.className}`}>
                    {risk.text}
                  </span>
                  {tip.historical_market_accuracy != null && (
                    <span className="text-xs px-2 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                      Market accuracy {formatPercent(tip.historical_market_accuracy, { digits: 0 })}
                    </span>
                  )}
                </div>

                {tip.reason && <p className="text-sm text-slate-600 mb-3">{tip.reason}</p>}

                <p className="text-[11px] text-slate-400 mb-3">
                  Sample size {tip.sample_size ?? "—"} · Score {tip.best_tip_score ?? "—"}
                  {isSuperAdmin && " · Admin: shadow tips available in Elite Shadow Preview only"}
                </p>

                {fixtureId && (
                  <Link
                    to={`/matches/${fixtureId}`}
                    className="text-sm font-medium text-amber-600 hover:text-amber-700"
                  >
                    Open in Match Center →
                  </Link>
                )}
              </SaasCard>
            );
          })}
        </div>
      )}

      {disclaimer && !loading && (
        <p className="text-xs text-slate-400 text-center">{disclaimer}</p>
      )}
    </div>
  );
}
