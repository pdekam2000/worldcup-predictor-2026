import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Beaker, ChevronDown, ChevronUp, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchOwnerEcseOddalertsShadow, fetchOwnerEcseOddalertsShadowMonitor } from "@/api/saasApi";

const BADGE_COLORS = {
  STRONG_SHADOW_SIGNAL: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  MEDIUM_SHADOW_SIGNAL: "bg-sky-500/20 text-sky-300 border-sky-500/40",
  WEAK_SHADOW_SIGNAL: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  WATCH_ONLY: "bg-slate-500/20 text-slate-300 border-slate-500/40",
  DO_NOT_USE: "bg-red-500/20 text-red-300 border-red-500/40",
};

const SEGMENT_FILTERS = [
  { value: "", label: "All segments" },
  { value: "STRONG_SHADOW_SIGNAL", label: "Strong signal" },
  { value: "MEDIUM_SHADOW_SIGNAL", label: "Medium signal" },
  { value: "WEAK_SHADOW_SIGNAL", label: "Weak signal" },
  { value: "WATCH_ONLY", label: "Watch only" },
  { value: "DO_NOT_USE", label: "Do not use" },
];

const STATUS_FILTERS = [
  { value: "all", label: "All" },
  { value: "finished", label: "Finished" },
  { value: "upcoming", label: "Upcoming" },
];

const PROMO_FILTERS = [
  { value: "", label: "All sources" },
  { value: "inserted", label: "Inserted" },
  { value: "enriched", label: "Enriched" },
];

function StatCard({ label, value, sub }) {
  return (
    <div className="glass rounded-xl p-4">
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      <div className="text-2xl font-display font-bold">{value ?? "—"}</div>
      {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
    </div>
  );
}

function Badge({ badge }) {
  const cls = BADGE_COLORS[badge] || "bg-muted text-muted-foreground";
  return (
    <span className={`inline-flex px-2 py-0.5 rounded border text-xs font-medium ${cls}`}>
      {badge?.replace(/_/g, " ") || "—"}
    </span>
  );
}

function HitCell({ hit }) {
  if (hit === null || hit === undefined) return <span className="text-muted-foreground">—</span>;
  return hit ? <span className="text-emerald-400">✓</span> : <span className="text-red-400/80">✗</span>;
}

function ExpandedRow({ row }) {
  return (
    <tr>
      <td colSpan={14} className="p-0 bg-muted/20">
        <div className="p-4 grid md:grid-cols-2 gap-4 text-sm">
          <div className="glass rounded-lg p-3">
            <h4 className="font-semibold mb-2">Top 10 exact scores</h4>
            <ol className="space-y-1">
              {(row.top_10_scores || []).map((s) => (
                <li key={s.rank || s.scoreline} className="flex justify-between">
                  <span>
                    {s.rank}. {s.scoreline}
                    {row.final_score === s.scoreline && " ✓"}
                  </span>
                  <span className="text-muted-foreground">
                    {s.probability != null ? `${(s.probability * 100).toFixed(1)}%` : ""}
                  </span>
                </li>
              ))}
            </ol>
          </div>
          <div className="space-y-3">
            <div className="glass rounded-lg p-3">
              <h4 className="font-semibold mb-2">Segment v2 ({row.segment_model_version || "v2 calibrated"})</h4>
              <p className="text-xs text-muted-foreground mb-2">
                Expected Top-3: {row.expected_top3_rate != null ? `${(row.expected_top3_rate * 100).toFixed(1)}%` : "—"}
                {" · "}
                Top-5: {row.expected_top5_rate != null ? `${(row.expected_top5_rate * 100).toFixed(1)}%` : "—"}
              </p>
              <ul className="list-disc pl-4 text-muted-foreground">
                {(row.segment_reasons_v2 || row.segment_reasons || []).map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              {(row.segment_cautions_v2 || row.segment_cautions || []).length > 0 && (
                <>
                  <h4 className="font-semibold mt-3 mb-2 text-amber-400">Cautions</h4>
                  <ul className="list-disc pl-4 text-amber-200/80">
                    {(row.segment_cautions_v2 || row.segment_cautions || []).map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
            <div className="glass rounded-lg p-3">
              <h4 className="font-semibold mb-2">Source trace</h4>
              <p className="text-xs text-muted-foreground">
                {row.source_provider} / {row.source_detail}
              </p>
              <p className="text-xs mt-1">Snapshot #{row.odds_snapshot_id}</p>
              <p className="text-xs mt-1">Crosswalk: {row.crosswalk_confidence || "—"}</p>
              <p className="text-xs mt-1">
                Bookmakers: {(row.source_bookmakers || []).slice(0, 6).join(", ")}
                {(row.source_bookmakers || []).length > 6 ? "…" : ""}
              </p>
              <p className="text-xs mt-1">Files: {(row.source_files || []).length} CSV refs</p>
              <p className="text-xs mt-1">Row hashes: {(row.source_row_hashes || []).length}</p>
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

export default function OwnerEcseOddalertsShadow() {
  const [tab, setTab] = useState("historical");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);

  const [competition, setCompetition] = useState("");
  const [team, setTeam] = useState("");
  const [status, setStatus] = useState("all");
  const [promotionAction, setPromotionAction] = useState("");
  const [segmentRecommendation, setSegmentRecommendation] = useState("");
  const [top1Outcome, setTop1Outcome] = useState("");
  const [bookmakerAgreementMin, setBookmakerAgreementMin] = useState("");
  const [monitorDateFrom, setMonitorDateFrom] = useState("2026-07-01");
  const [monitorDateTo, setMonitorDateTo] = useState("2026-07-07");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res =
        tab === "monitor"
          ? await fetchOwnerEcseOddalertsShadowMonitor({
              dateFrom: monitorDateFrom,
              dateTo: monitorDateTo,
              status,
              limit: 200,
            })
          : await fetchOwnerEcseOddalertsShadow({
              competition: competition || undefined,
              team: team || undefined,
              status,
              promotionAction: promotionAction || undefined,
              segmentRecommendation: segmentRecommendation || undefined,
              top1Outcome: top1Outcome || undefined,
              bookmakerAgreementMin: bookmakerAgreementMin === "" ? undefined : Number(bookmakerAgreementMin),
              limit: 200,
            });
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load OddAlerts ECSE shadow lab");
    } finally {
      setLoading(false);
    }
  }, [
    tab,
    monitorDateFrom,
    monitorDateTo,
    competition,
    team,
    status,
    promotionAction,
    segmentRecommendation,
    top1Outcome,
    bookmakerAgreementMin,
  ]);

  useEffect(() => {
    load();
  }, [load]);

  const summary = data?.summary || {};
  const evalStats = data?.evaluation_stats || {};
  const items = data?.items || [];
  const isMonitor = tab === "monitor";

  return (
    <div className="space-y-6 pb-12">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 text-primary mb-1">
            <Beaker className="w-5 h-5" />
            <span className="text-sm font-medium uppercase tracking-wide">Owner research lab only</span>
          </div>
          <h1 className="text-3xl font-display font-bold">ECSE OddAlerts Shadow</h1>
          <p className="text-muted-foreground mt-1 max-w-2xl">
            Shadow ECSE exact-score predictions from OddAlerts CSV policy odds. Not published to public
            predictions. v2 calibrated segments ({data?.segment_model_version || "oddalerts_ecse_segments_v2_calibrated"}).
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <div className="flex gap-2 border-b border-border/60 pb-2">
        <button
          type="button"
          className={`px-4 py-2 text-sm rounded-t-lg ${tab === "historical" ? "bg-primary/20 text-primary font-medium" : "text-muted-foreground"}`}
          onClick={() => setTab("historical")}
        >
          Historical Shadow
        </button>
        <button
          type="button"
          className={`px-4 py-2 text-sm rounded-t-lg ${tab === "monitor" ? "bg-primary/20 text-primary font-medium" : "text-muted-foreground"}`}
          onClick={() => setTab("monitor")}
        >
          Live Shadow Monitor
        </button>
      </div>

      <div className="flex items-start gap-2 p-3 rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-200 text-sm">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
        Owner/internal only — no production ECSE writes. Research signal, not betting advice.
      </div>

      {error && (
        <div className="p-4 rounded-lg border border-red-500/40 bg-red-500/10 text-red-200">{error}</div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        {isMonitor ? (
          <>
            <StatCard label="Monitored" value={data?.total ?? items.length} />
            <StatCard label="Upcoming" value={items.filter((i) => !i.finished).length} />
            <StatCard label="Finished" value={items.filter((i) => i.finished).length} />
          </>
        ) : (
          <>
            <StatCard label="Shadow records" value={summary.total_shadow_records} />
            <StatCard label="Finished" value={summary.finished_count} sub={`${summary.upcoming_count || 0} upcoming`} />
            <StatCard
              label="Top-1 hit"
              value={evalStats.top1_hit_rate != null ? `${(evalStats.top1_hit_rate * 100).toFixed(1)}%` : "—"}
            />
            <StatCard
              label="Top-3 hit"
              value={evalStats.top3_hit_rate != null ? `${(evalStats.top3_hit_rate * 100).toFixed(1)}%` : "—"}
            />
            <StatCard label="Strong v2" value={summary.strong_signal_count_v2} sub={`v1: ${summary.strong_signal_count ?? "—"}`} />
            <StatCard label="Do not use v1" value={summary.do_not_use_count} />
          </>
        )}
      </div>

      <div className="glass rounded-xl p-4 flex flex-wrap gap-3 items-end">
        {isMonitor && (
          <>
            <label className="text-sm">
              <span className="text-muted-foreground block mb-1">From</span>
              <input type="date" className="bg-background border rounded px-2 py-1.5 text-sm" value={monitorDateFrom} onChange={(e) => setMonitorDateFrom(e.target.value)} />
            </label>
            <label className="text-sm">
              <span className="text-muted-foreground block mb-1">To</span>
              <input type="date" className="bg-background border rounded px-2 py-1.5 text-sm" value={monitorDateTo} onChange={(e) => setMonitorDateTo(e.target.value)} />
            </label>
          </>
        )}
        {!isMonitor && (
        <>
        <label className="text-sm">
          <span className="text-muted-foreground block mb-1">Competition</span>
          <select
            className="bg-background border rounded px-2 py-1.5 text-sm min-w-[140px]"
            value={competition}
            onChange={(e) => setCompetition(e.target.value)}
          >
            <option value="">All</option>
            <option value="premier_league">Premier League</option>
            <option value="bundesliga">Bundesliga</option>
            <option value="world_cup_2026">World Cup 2026</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="text-muted-foreground block mb-1">Source</span>
          <select
            className="bg-background border rounded px-2 py-1.5 text-sm"
            value={promotionAction}
            onChange={(e) => setPromotionAction(e.target.value)}
          >
            {PROMO_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="text-muted-foreground block mb-1">Segment</span>
          <select
            className="bg-background border rounded px-2 py-1.5 text-sm min-w-[160px]"
            value={segmentRecommendation}
            onChange={(e) => setSegmentRecommendation(e.target.value)}
          >
            {SEGMENT_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="text-muted-foreground block mb-1">Top-1 outcome</span>
          <select
            className="bg-background border rounded px-2 py-1.5 text-sm"
            value={top1Outcome}
            onChange={(e) => setTop1Outcome(e.target.value)}
          >
            <option value="">All</option>
            <option value="home">Home</option>
            <option value="draw">Draw</option>
            <option value="away">Away</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="text-muted-foreground block mb-1">Team search</span>
          <input
            className="bg-background border rounded px-2 py-1.5 text-sm"
            value={team}
            onChange={(e) => setTeam(e.target.value)}
            placeholder="Team name"
          />
        </label>
        <label className="text-sm">
          <span className="text-muted-foreground block mb-1">Bookmaker agree min</span>
          <select
            className="bg-background border rounded px-2 py-1.5 text-sm"
            value={bookmakerAgreementMin}
            onChange={(e) => setBookmakerAgreementMin(e.target.value)}
          >
            <option value="">Any</option>
            <option value="1">Agrees only</option>
          </select>
        </label>
        </>
        )}
        <label className="text-sm">
          <span className="text-muted-foreground block mb-1">Status</span>
          <select
            className="bg-background border rounded px-2 py-1.5 text-sm"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            {STATUS_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="glass rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/60 text-left text-muted-foreground">
                <th className="p-3 w-8" />
                <th className="p-3">Match</th>
                <th className="p-3">Competition</th>
                <th className="p-3">Date</th>
                <th className="p-3">Final</th>
                <th className="p-3">Top 1</th>
                <th className="p-3">Top 3</th>
                <th className="p-3">Hits</th>
                <th className="p-3">Lambda</th>
                <th className="p-3">Market</th>
                <th className="p-3">WDE</th>
                <th className="p-3">Segment v2</th>
                <th className="p-3">v1</th>
                <th className="p-3">Source</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={14} className="p-8 text-center text-muted-foreground">
                    Loading shadow predictions…
                  </td>
                </tr>
              )}
              {!loading &&
                items.map((row) => (
                  <React.Fragment key={row.fixture_id}>
                    <tr className="border-b border-border/40 hover:bg-muted/30">
                      <td className="p-3">
                        <button
                          type="button"
                          className="text-muted-foreground hover:text-foreground"
                          onClick={() =>
                            setExpanded(expanded === row.fixture_id ? null : row.fixture_id)
                          }
                        >
                          {expanded === row.fixture_id ? (
                            <ChevronUp className="w-4 h-4" />
                          ) : (
                            <ChevronDown className="w-4 h-4" />
                          )}
                        </button>
                      </td>
                      <td className="p-3 font-medium whitespace-nowrap">
                        {row.home_team} vs {row.away_team}
                      </td>
                      <td className="p-3 text-muted-foreground">{row.competition}</td>
                      <td className="p-3 text-muted-foreground whitespace-nowrap">
                        {(row.kickoff_utc || "").slice(0, 10)}
                      </td>
                      <td className="p-3">{row.final_score || "—"}</td>
                      <td className="p-3 font-mono">{row.top_1_score}</td>
                      <td className="p-3 font-mono text-xs">{(row.top_3_scores || []).join(", ")}</td>
                      <td className="p-3">
                        <HitCell hit={row.top1_hit} />
                        <HitCell hit={row.top3_hit} />
                        <HitCell hit={row.top5_hit} />
                      </td>
                      <td className="p-3 font-mono text-xs">
                        {Number(row.lambda_home).toFixed(2)}/{Number(row.lambda_away).toFixed(2)}
                      </td>
                      <td className="p-3 text-xs">{row.bookmaker_implied_direction || "—"}</td>
                      <td className="p-3 text-xs">
                        {row.wde_agrees === true ? "✓" : row.wde_agrees === false ? "✗" : "—"}
                      </td>
                      <td className="p-3">
                        <Badge badge={row.segment_badge_v2 || row.segment_badge} />
                        <div className="text-xs text-muted-foreground mt-1">
                          {row.segment_score_v2 ?? row.segment_score}
                          {row.top5_value_signal && " · TOP5"}
                        </div>
                      </td>
                      <td className="p-3">
                        <span className="text-xs text-muted-foreground">{row.segment_badge}</span>
                      </td>
                      <td className="p-3 text-xs">
                        {isMonitor ? row.promotion_eligibility_v2 : row.promotion_action}
                      </td>
                    </tr>
                    {expanded === row.fixture_id && <ExpandedRow row={row} />}
                  </React.Fragment>
                ))}
              {!loading && items.length === 0 && (
                <tr>
                  <td colSpan={14} className="p-8 text-center text-muted-foreground">
                    No rows match filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="p-3 text-xs text-muted-foreground border-t border-border/40">
          Showing {items.length} of {data?.total ?? 0} filtered · run {data?.shadow_run_id}
        </div>
      </div>
    </div>
  );
}
