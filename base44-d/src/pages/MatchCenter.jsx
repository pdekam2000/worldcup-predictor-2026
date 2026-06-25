import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Search, Calendar, Target, AlertCircle, RefreshCw,
  ChevronLeft, ChevronRight, Radio, CheckCircle2, List, Sparkles, Globe2, Medal,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { fetchMatches } from "@/api/worldcupApi";
import { SectionHeader, PredictionCard, TerminalCard } from "@/components/terminal";

const STATUS_TABS = [
  { id: "upcoming", label: "Upcoming", icon: Calendar },
  { id: "live", label: "Live", icon: Radio },
  { id: "finished", label: "Finished", icon: CheckCircle2 },
  { id: "all", label: "All", icon: List },
  { id: "predicted", label: "Predicted", icon: Sparkles },
];

const HUB_TABS = [
  { id: "all", label: "All", icon: List },
  { id: "worldcup", label: "World Cup 2026", icon: Globe2 },
  { id: "leagues", label: "Leagues", icon: Medal },
];

const PAGE_SIZE = 50;

function isWorldCupMatch(m) {
  const l = String(m.league || m.competition_key || "").toLowerCase();
  return l.includes("world cup") || l.includes("world_cup") || l.includes("fifa");
}

export default function MatchCenter() {
  const [searchParams, setSearchParams] = useSearchParams();
  const hub = searchParams.get("hub") || "all";

  const [matches, setMatches] = useState([]);
  const [search, setSearch] = useState("");
  const [leagueFilter, setLeagueFilter] = useState("All Leagues");
  const [predictionFilter, setPredictionFilter] = useState("all");
  const [statusTab, setStatusTab] = useState(() => searchParams.get("status") || "upcoming");
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [predictedCount, setPredictedCount] = useState(0);
  const [sourceLabel, setSourceLabel] = useState(null);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(null);

  const setHub = (id) => {
    const next = new URLSearchParams(searchParams);
    if (id === "all") next.delete("hub");
    else next.set("hub", id);
    setSearchParams(next, { replace: true });
  };

  const loadMatches = useCallback(async () => {
    setLoading(true);
    setApiError(null);
    try {
      const hasPrediction =
        predictionFilter === "yes" ? true : predictionFilter === "no" ? false : undefined;
      const result = await fetchMatches({
        status: statusTab,
        page,
        page_size: PAGE_SIZE,
        team: search.trim() || undefined,
        has_prediction: hasPrediction,
      });
      setMatches(result.matches);
      setTotalCount(result.total_count);
      setTotalPages(result.total_pages || 1);
      setPredictedCount(result.predicted_fixture_count);
      setSourceLabel(result.source_label);
    } catch (err) {
      setMatches([]);
      setApiError(err instanceof Error ? err.message : "Failed to load matches from API.");
    } finally {
      setLoading(false);
    }
  }, [statusTab, page, search, predictionFilter]);

  useEffect(() => {
    loadMatches();
  }, [loadMatches]);

  useEffect(() => {
    setPage(1);
  }, [statusTab, search, predictionFilter, hub]);

  const hubFiltered = useMemo(() => {
    if (hub === "worldcup") return matches.filter(isWorldCupMatch);
    if (hub === "leagues") return matches.filter((m) => !isWorldCupMatch(m));
    return matches;
  }, [matches, hub]);

  const leagueOptions = [
    "All Leagues",
    ...Array.from(new Set(hubFiltered.map((m) => m.league).filter(Boolean))).sort(),
  ];

  const filtered = hubFiltered.filter((m) => leagueFilter === "All Leagues" || m.league === leagueFilter);

  const hubTitle =
    hub === "worldcup" ? "World Cup Center" : hub === "leagues" ? "League Center" : "Match Center";
  const hubSubtitle =
    hub === "worldcup"
      ? "FIFA World Cup 2026 — groups, flags, fixtures & predictions"
      : hub === "leagues"
        ? "Club leagues separated from international tournaments"
        : "Browse all fixtures — filter by status, league, and predictions";

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <SectionHeader
        eyebrow={hub === "worldcup" ? "🏆 International" : hub === "leagues" ? "⚽ Clubs" : "Fixtures"}
        title={hubTitle}
        subtitle={hubSubtitle}
      />

      <div className="flex flex-wrap gap-2">
        {HUB_TABS.map((tab) => {
          const Icon = tab.icon;
          const active = hub === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setHub(tab.id)}
              className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold transition-all border ${
                active
                  ? "bg-[#00E676]/15 text-[#00E676] border-[#00E676]/30"
                  : "bg-[#101827] text-[#94A3B8] border-white/[0.06] hover:border-white/15"
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
        <Button
          variant="outline"
          size="sm"
          onClick={loadMatches}
          disabled={loading}
          className="ml-auto border-white/10 bg-[#101827]"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </Button>
      </div>

      {!loading && !apiError && (
        <p className="text-xs text-[#94A3B8]">
          {filtered.length} shown · {totalCount} total
          {predictedCount > 0 && ` · ${predictedCount} predicted`}
          {sourceLabel && ` · ${sourceLabel}`}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {STATUS_TABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setStatusTab(tab.id)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                statusTab === tab.id
                  ? "bg-[#3B82F6] text-white"
                  : "bg-white/5 text-[#94A3B8] hover:bg-white/10"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          );
        })}
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#94A3B8]" />
          <Input
            placeholder="Search teams…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10 bg-[#101827] border-white/10 rounded-xl text-[#F8FAFC]"
            disabled={loading && matches.length === 0}
          />
        </div>
        <Select value={leagueFilter} onValueChange={setLeagueFilter}>
          <SelectTrigger className="w-full sm:w-48 bg-[#101827] border-white/10 rounded-xl">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-[#101827] border-white/10">
            {leagueOptions.map((l) => (
              <SelectItem key={l} value={l}>{l}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={predictionFilter} onValueChange={setPredictionFilter}>
          <SelectTrigger className="w-full sm:w-44 bg-[#101827] border-white/10 rounded-xl">
            <SelectValue placeholder="Prediction" />
          </SelectTrigger>
          <SelectContent className="bg-[#101827] border-white/10">
            <SelectItem value="all">Any prediction</SelectItem>
            <SelectItem value="yes">Has prediction</SelectItem>
            <SelectItem value="no">No prediction</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {apiError && (
        <TerminalCard className="text-center border-[#FF4D4D]/30">
          <AlertCircle className="w-10 h-10 mx-auto mb-3 text-[#FF4D4D]" />
          <p className="text-sm text-[#FF4D4D] mb-4">{apiError}</p>
          <Button type="button" variant="outline" size="sm" onClick={loadMatches}>Retry</Button>
        </TerminalCard>
      )}

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="w-8 h-8 border-2 border-[#00E676]/20 border-t-[#00E676] rounded-full animate-spin" />
        </div>
      ) : (
        !apiError && filtered.length > 0 && (
          <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {filtered.map((m, i) => (
              <motion.div
                key={m.id || i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.03, 0.3) }}
              >
                <PredictionCard
                  match={{
                    ...m,
                    prediction_1x2: m.prediction,
                    hybrid_confidence: m.hybrid_confidence,
                  }}
                  variant="match"
                />
              </motion.div>
            ))}
          </div>
        )
      )}

      {!loading && !apiError && matches.length === 0 && (
        <TerminalCard className="text-center py-12">
          <Target className="w-12 h-12 mx-auto mb-4 text-[#94A3B8] opacity-50" />
          <p className="text-[#94A3B8]">No matches in this view.</p>
        </TerminalCard>
      )}

      {!loading && !apiError && matches.length > 0 && filtered.length === 0 && (
        <TerminalCard className="text-center py-12 text-[#94A3B8]">
          No matches match your filters.
        </TerminalCard>
      )}

      {!loading && !apiError && totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))} className="border-white/10">
            <ChevronLeft className="w-4 h-4 mr-1" /> Previous
          </Button>
          <span className="text-sm text-[#94A3B8]">Page {page} of {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))} className="border-white/10">
            Next <ChevronRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      )}
    </div>
  );
}
