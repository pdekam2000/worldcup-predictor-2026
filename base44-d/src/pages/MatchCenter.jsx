import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { AlertCircle, RefreshCw, Trophy, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchMatches, fetchCompetitions } from "@/api/worldcupApi";
import { SectionHeader, TerminalCard } from "@/components/terminal";
import LeagueSelector from "@/components/match-center/LeagueSelector";
import MatchCenterFilters from "@/components/match-center/MatchCenterFilters";
import EliteMatchCard from "@/components/match-center/EliteMatchCard";
import BetSlipDrawer from "@/components/match-center/BetSlipDrawer";
import { applyClientFilters } from "@/lib/matchCenterUtils";

const PAGE_SIZE = 30;

export default function MatchCenter() {
  const [searchParams, setSearchParams] = useSearchParams();
  const competitionParam = searchParams.get("competition") || "all";

  const [competitions, setCompetitions] = useState([]);
  const [totalUpcoming, setTotalUpcoming] = useState(0);
  const [matches, setMatches] = useState([]);
  const [search, setSearch] = useState("");
  const [statusTab, setStatusTab] = useState(() => searchParams.get("status") || "upcoming");
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [predictedCount, setPredictedCount] = useState(0);
  const [sourceLabel, setSourceLabel] = useState(null);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(null);

  const [datePreset, setDatePreset] = useState("");
  const [highConfidence, setHighConfidence] = useState(false);
  const [eliteOnly, setEliteOnly] = useState(false);
  const [liveOnly, setLiveOnly] = useState(false);
  const [upcomingOnly, setUpcomingOnly] = useState(false);
  const [country, setCountry] = useState("all");

  const setCompetition = (key) => {
    const next = new URLSearchParams(searchParams);
    if (!key || key === "all") next.delete("competition");
    else next.set("competition", key);
    setSearchParams(next, { replace: true });
  };

  const loadCompetitions = useCallback(async () => {
    try {
      const res = await fetchCompetitions();
      setCompetitions(res.competitions || []);
      setTotalUpcoming(res.total_upcoming || 0);
    } catch {
      setCompetitions([]);
    }
  }, []);

  const loadMatches = useCallback(async () => {
    setLoading(true);
    setApiError(null);
    try {
      const result = await fetchMatches({
        status: statusTab,
        page,
        page_size: PAGE_SIZE,
        competition: competitionParam,
        country: country !== "all" ? country : undefined,
        include_summary: true,
        elite_only: eliteOnly,
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
  }, [statusTab, page, competitionParam, country, eliteOnly]);

  useEffect(() => {
    loadCompetitions();
  }, [loadCompetitions]);

  useEffect(() => {
    loadMatches();
  }, [loadMatches]);

  useEffect(() => {
    setPage(1);
  }, [statusTab, search, competitionParam, country, eliteOnly, datePreset, highConfidence, liveOnly, upcomingOnly]);

  const countries = useMemo(
    () => Array.from(new Set(competitions.map((c) => c.country).filter(Boolean))).sort(),
    [competitions]
  );

  const filtered = useMemo(
    () =>
      applyClientFilters(matches, {
        search,
        datePreset,
        highConfidence,
        eliteOnly: false,
        liveOnly,
        upcomingOnly,
      }),
    [matches, search, datePreset, highConfidence, liveOnly, upcomingOnly]
  );

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto pb-24">
      <SectionHeader
        eyebrow="⚽ Elite Hub"
        title="Match Center"
        subtitle="All fixtures from your connected API plan — predictions, markets, and combo intelligence in one place."
      />

      <LeagueSelector
        competitions={competitions}
        selectedKey={competitionParam}
        onSelect={setCompetition}
        totalUpcoming={totalUpcoming}
      />

      <MatchCenterFilters
        search={search}
        onSearchChange={setSearch}
        statusTab={statusTab}
        onStatusTabChange={setStatusTab}
        datePreset={datePreset}
        onDatePresetChange={setDatePreset}
        highConfidence={highConfidence}
        onHighConfidenceChange={setHighConfidence}
        eliteOnly={eliteOnly}
        onEliteOnlyChange={setEliteOnly}
        liveOnly={liveOnly}
        onLiveOnlyChange={setLiveOnly}
        upcomingOnly={upcomingOnly}
        onUpcomingOnlyChange={setUpcomingOnly}
        country={country}
        onCountryChange={setCountry}
        countries={countries}
      />

      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-[#94A3B8]">
          {filtered.length} shown · {totalCount} total
          {predictedCount > 0 && ` · ${predictedCount} with predictions`}
          {sourceLabel && ` · ${sourceLabel}`}
        </p>
        <Button variant="outline" size="sm" onClick={() => { loadCompetitions(); loadMatches(); }} disabled={loading} className="border-white/10">
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </Button>
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
          <div className="w-10 h-10 border-2 border-[#00E676]/20 border-t-[#00E676] rounded-full animate-spin" />
        </div>
      ) : (
        !apiError && filtered.length > 0 && (
          <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {filtered.map((m, i) => (
              <motion.div
                key={`${m.competition_key || ""}-${m.id || m.fixture_id}`}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.02, 0.25) }}
              >
                <EliteMatchCard match={m} />
              </motion.div>
            ))}
          </div>
        )
      )}

      {!loading && !apiError && matches.length === 0 && (
        <TerminalCard className="text-center py-16">
          <Trophy className="w-12 h-12 mx-auto mb-4 text-[#94A3B8] opacity-50" />
          <p className="text-[#94A3B8]">No matches in this view.</p>
        </TerminalCard>
      )}

      {!loading && !apiError && matches.length > 0 && filtered.length === 0 && (
        <TerminalCard className="text-center py-12 text-[#94A3B8]">No matches match your filters.</TerminalCard>
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

      <BetSlipDrawer />
    </div>
  );
}
