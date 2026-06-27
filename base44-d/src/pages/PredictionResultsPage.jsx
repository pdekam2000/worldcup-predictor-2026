import React, { useCallback, useEffect, useMemo, useState } from "react";

import { Link } from "react-router-dom";

import { motion, AnimatePresence } from "framer-motion";

import {

  Trophy,

  RefreshCw,

  AlertCircle,

  CheckCircle2,

  XCircle,

  Clock,

  ChevronDown,

  ChevronUp,

  BarChart3,

} from "lucide-react";

import { fetchEvaluatedResults } from "@/api/saasApi";

import { Button } from "@/components/ui/button";

import MatchTeamsRow from "@/components/match/MatchTeamsRow";

import { getArchiveStatusConfig, pick1x2Label } from "@/lib/archiveStatus";

import { MARKET_FILTERS, marketViewForItem } from "@/lib/archiveFilters";

import MarketBreakdownPanel from "@/components/archive/MarketBreakdownPanel";



const RANGE_TABS = [

  { id: "yesterday", label: "Yesterday" },

  { id: "7d", label: "Last 7 days" },

  { id: "30d", label: "Last 30 days" },

  { id: "all", label: "All evaluated" },

];



const STATUS_TABS = [

  { id: "all", label: "All" },

  { id: "evaluated", label: "Evaluated" },

  { id: "correct", label: "Correct" },

  { id: "wrong", label: "Wrong" },

  { id: "partial", label: "Partial" },

  { id: "pending", label: "Pending" },

];



function formatKickoff(value) {

  if (!value) return "—";

  try {

    return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

  } catch {

    return "—";

  }

}



function displayPredicted(item, marketFilter) {

  const view = item.filtered_market_view || marketViewForItem(item, marketFilter);

  if (view?.display_pick) return view.display_pick;

  if (view?.predicted_pick) return view.predicted_pick;

  const pred = item.predicted_pick || item.prediction_summary?.best_pick;

  return pick1x2Label(pred) || pred || "—";

}



function ResultCard({ item, index, marketFilter }) {

  const [open, setOpen] = useState(false);

  const statusKey = item.filtered_market_status || item.overall_status || item.result_status || "pending";

  const cfg = getArchiveStatusConfig(statusKey);

  const Icon = cfg.icon;

  const breakdown = item.market_breakdown || [];

  const marketView = item.filtered_market_view || marketViewForItem(item, marketFilter);



  return (

    <motion.article

      initial={{ opacity: 0, y: 8 }}

      animate={{ opacity: 1, y: 0 }}

      transition={{ delay: Math.min(index * 0.03, 0.3) }}

      className={`rounded-xl border p-4 bg-white shadow-sm ${cfg.card}`}

    >

      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">

        <div className="min-w-0 flex-1 space-y-3">

          <div className="flex items-center gap-2 text-xs text-slate-500">

            <Trophy className="w-3.5 h-3.5 text-amber-500" />

            <span>{item.competition || "Competition"}</span>

            <span>·</span>

            <span>{formatKickoff(item.kickoff || item.match_date)}</span>

          </div>

          <MatchTeamsRow homeTeam={item.home_team} awayTeam={item.away_team} size="md" />

          {item.limited_historical_payload && (

            <p className="text-xs text-slate-500 italic">Limited historical payload — only stored markets are evaluated.</p>

          )}

          <div className="grid sm:grid-cols-3 gap-2 text-sm">

            <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2">

              <div className="text-[10px] uppercase tracking-wide text-slate-500">

                {marketView?.market_label || "Predicted"}

              </div>

              <div className="font-medium text-slate-900">{displayPredicted(item, marketFilter)}</div>

            </div>

            <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2">

              <div className="text-[10px] uppercase tracking-wide text-slate-500">Final score</div>

              <div className="font-mono font-semibold text-slate-900">{item.final_score || "—"}</div>

            </div>

            <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2">

              <div className="text-[10px] uppercase tracking-wide text-slate-500">Outcome</div>

              <div className="text-slate-600 capitalize">{(item.actual_result || "—").replace(/_/g, " ")}</div>

            </div>

          </div>

        </div>

        <div className="flex flex-col items-start sm:items-end gap-2 shrink-0">

          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${cfg.badge}`}>

            <Icon className="w-3.5 h-3.5" />

            {cfg.label}

          </span>

          {item.is_quarantined && (

            <span className="text-[10px] px-2 py-0.5 rounded border border-amber-400 text-amber-900 bg-amber-100">

              Data quarantine

            </span>

          )}

          <div className="text-[10px] text-slate-500 tabular-nums">

            {item.correct_markets_count ?? 0} correct · {item.wrong_markets_count ?? 0} wrong ·{" "}

            {item.unavailable_markets_count ?? 0} unavailable

          </div>

          <div className="flex flex-wrap gap-2">

            <Button asChild variant="outline" size="sm" className="border-amber-300 h-8 text-xs">

              <Link to={item.detail_url || `/matches/${item.fixture_id}`}>Match detail</Link>

            </Button>

            {item.archive_entry_id && (

              <Button asChild variant="outline" size="sm" className="border-amber-300 h-8 text-xs">

                <Link to={`/archive/${item.archive_entry_id}`}>Archive</Link>

              </Button>

            )}

          </div>

        </div>

      </div>



      {breakdown.length > 0 && (

        <div className="mt-4 border-t border-amber-100 pt-3">

          <button

            type="button"

            onClick={() => setOpen((v) => !v)}

            className="flex items-center gap-2 text-xs text-amber-800 hover:text-amber-900"

          >

            {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}

            Market breakdown ({breakdown.length})

          </button>

          <AnimatePresence>

            {open && (

              <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">

                <MarketBreakdownPanel rows={breakdown} />

              </motion.div>

            )}

          </AnimatePresence>

        </div>

      )}

    </motion.article>

  );

}



export default function PredictionResultsPage() {

  const [range, setRange] = useState("all");

  const [status, setStatus] = useState("all");

  const [market, setMarket] = useState("best_bets");

  const [results, setResults] = useState([]);

  const [counts, setCounts] = useState({ correct: 0, wrong: 0, partial: 0, pending: 0 });

  const [winrate, setWinrate] = useState(null);

  const [totalCount, setTotalCount] = useState(0);

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState(null);



  const load = useCallback(async () => {

    setLoading(true);

    setError(null);

    try {

      const apiStatus = status === "evaluated" ? "all" : status;

      const utcOffsetMinutes = -new Date().getTimezoneOffset();

      const data = await fetchEvaluatedResults({

        range,

        status: apiStatus,

        market,

        limit: 200,

        utcOffsetMinutes,

      });

      let rows = data.results || [];

      if (status === "evaluated") {

        rows = rows.filter((r) => ["correct", "wrong", "partial"].includes(r.overall_status));

      } else if (status !== "all") {

        rows = rows.filter((r) => r.overall_status === status);

      }

      setResults(rows);

      setCounts(data.counts || {});

      setWinrate(data.winrate || null);

      setTotalCount(data.total_count ?? rows.length);

    } catch (err) {

      setResults([]);

      setError(err instanceof Error ? err.message : "Failed to load results");

    } finally {

      setLoading(false);

    }

  }, [range, status, market]);



  useEffect(() => {

    load();

  }, [load]);



  const summaryCards = useMemo(

    () => [

      { label: "Total", value: totalCount, color: "text-slate-900", icon: BarChart3 },

      { label: "Correct", value: counts.correct ?? 0, color: "text-emerald-700", icon: CheckCircle2 },

      { label: "Wrong", value: counts.wrong ?? 0, color: "text-red-600", icon: XCircle },

      { label: "Partial", value: counts.partial ?? 0, color: "text-violet-700", icon: Clock },

      { label: "Best Bet Winrate", value: winrate?.best_bet_winrate?.accuracy != null ? `${winrate.best_bet_winrate.accuracy}%` : "—", color: "text-amber-800", icon: Trophy },

    ],

    [totalCount, counts, winrate]

  );



  return (

    <div className="space-y-6 max-w-5xl mx-auto px-1 sm:px-0 pb-12 bg-gradient-to-b from-amber-50/80 to-white min-h-screen">

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">

        <div>

          <h1 className="text-2xl sm:text-3xl font-display font-bold flex items-center gap-2 text-slate-900">

            <CheckCircle2 className="w-7 h-7 text-amber-500" />

            Prediction Results

          </h1>

          <p className="text-sm text-slate-600 mt-1">

            Each market evaluated separately. Default view: program best bets only. Public winrate excludes no_bet and research-only picks.

          </p>

        </div>

        <div className="flex gap-2 flex-wrap">

          <Button asChild variant="outline" size="sm" className="border-amber-300">

            <Link to="/archive">Archive</Link>

          </Button>

          <Button asChild variant="outline" size="sm" className="border-amber-300">

            <Link to="/matches?status=finished">Match Center · Finished</Link>

          </Button>

          <Button variant="outline" size="sm" onClick={load} disabled={loading} className="border-amber-300">

            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />

          </Button>

        </div>

      </div>



      {error && (

        <div className="rounded-xl border border-red-300 bg-red-50 p-4 flex items-center gap-2 text-red-800 text-sm">

          <AlertCircle className="w-4 h-4" /> {error}

        </div>

      )}



      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">

        {summaryCards.map((s) => (

          <div key={s.label} className="rounded-xl border border-amber-200 bg-white p-4 text-center shadow-sm">

            <div className={`text-2xl font-bold tabular-nums ${s.color}`}>{loading ? "…" : s.value}</div>

            <div className="text-xs text-slate-500 mt-1">{s.label}</div>

          </div>

        ))}

      </div>



      <div className="rounded-xl border border-amber-200 bg-white p-4 space-y-3 shadow-sm">

        <div className="flex flex-wrap gap-2">

          {RANGE_TABS.map((t) => (

            <button

              key={t.id}

              type="button"

              onClick={() => setRange(t.id)}

              className={`px-3 py-1.5 rounded-lg text-xs border ${

                range === t.id ? "bg-amber-400 text-slate-900 border-amber-500 font-semibold" : "bg-amber-50 text-slate-600 border-amber-200"

              }`}

            >

              {t.label}

            </button>

          ))}

        </div>

        <div className="flex flex-wrap gap-2">

          {STATUS_TABS.map((t) => (

            <button

              key={t.id}

              type="button"

              onClick={() => setStatus(t.id)}

              className={`px-3 py-1.5 rounded-lg text-xs border ${

                status === t.id ? "bg-emerald-100 text-emerald-800 border-emerald-300" : "bg-amber-50 text-slate-600 border-amber-200"

              }`}

            >

              {t.label}

            </button>

          ))}

        </div>

        <div className="flex flex-wrap gap-2 items-center">

          <span className="text-xs text-slate-500">Market:</span>

          {MARKET_FILTERS.map((t) => (

            <button

              key={t.id}

              type="button"

              onClick={() => setMarket(t.id)}

              className={`px-3 py-1.5 rounded-lg text-xs border ${

                market === t.id ? "bg-amber-400 text-slate-900 border-amber-500 font-semibold" : "bg-amber-50 text-slate-600 border-amber-200"

              }`}

            >

              {t.label}

            </button>

          ))}

        </div>

      </div>



      {loading ? (

        <div className="flex justify-center py-16">

          <div className="w-8 h-8 border-2 border-amber-200 border-t-amber-500 rounded-full animate-spin" />

        </div>

      ) : results.length === 0 ? (

        <div className="text-center py-16 rounded-2xl border border-amber-200 bg-white px-4">

          <Trophy className="w-12 h-12 mx-auto text-amber-300 mb-3" />

          <p className="font-medium text-slate-900">No evaluated results in this view</p>

          <p className="text-sm text-slate-500 mt-2">Try a wider date range or another market filter.</p>

          <Link to="/archive" className="text-amber-700 text-sm mt-4 inline-block hover:underline">

            Open Prediction Archive

          </Link>

        </div>

      ) : (

        <div className="space-y-3">

          {results.map((item, i) => (

            <ResultCard key={item.fixture_id} item={item} index={i} marketFilter={market} />

          ))}

        </div>

      )}

    </div>

  );

}


