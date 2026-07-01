import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Beaker, ChevronRight, RefreshCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  fetchOwnerEcseShadowLabSummary,
  fetchOwnerEcseShadowLabFixtures,
  fetchOwnerEcseShadowLabFixture,
} from "@/api/saasApi";

const FILTERS = [
  { value: "all", label: "All" },
  { value: "applied", label: "Applied only" },
  { value: "evaluated", label: "Evaluated only" },
  { value: "pending", label: "Pending only" },
  { value: "strong_home", label: "Strong home (≥60%)" },
  { value: "home_favorite", label: "Home favorite (≥55%)" },
  { value: "missing_odds", label: "Missing odds" },
  { value: "balanced", label: "Balanced excluded" },
  { value: "enhanced_better", label: "Enhanced better" },
  { value: "enhanced_worse", label: "Enhanced worse" },
  { value: "no_change", label: "No change" },
  { value: "x3_available", label: "X3 available" },
  { value: "x3_unavailable", label: "X3 unavailable" },
];

function StatCard({ label, value, sub, warn }) {
  return (
    <div className={`glass rounded-xl p-4 ${warn ? "border border-amber-500/40" : ""}`}>
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      <div className={`text-2xl font-display font-bold ${warn ? "text-amber-400" : ""}`}>{value ?? "—"}</div>
      {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
    </div>
  );
}

function pctBlock(metrics, key) {
  const m = metrics?.[key];
  if (!m) return "—";
  return `${m.baseline_pct}% → ${m.enhanced_pct}% (Δ ${m.delta_pp >= 0 ? "+" : ""}${m.delta_pp}pp)`;
}

function exclusionLabel(reason) {
  if (!reason) return "—";
  if (reason === "missing_ft_home" || reason === "invalid_odds_snapshot") return "Skipped: missing odds";
  if (reason === "balanced_match") return "Skipped: balanced match";
  return reason.replace(/_/g, " ");
}

function deltaLabel(row) {
  if (row.enhanced_better) return "Enhanced better";
  if (row.enhanced_worse) return "Enhanced worse";
  if (row.unchanged) return "No change";
  return "—";
}

function movementArrow(movement) {
  if (movement > 0) return `↑${movement}`;
  if (movement < 0) return `↓${Math.abs(movement)}`;
  return "→";
}

function Top10Panel({ title, rows, actualScore, movements }) {
  return (
    <div className="glass rounded-xl p-4">
      <h3 className="font-semibold mb-3">{title}</h3>
      <ol className="space-y-1 text-sm">
        {(rows || []).map((r) => {
          const hit = actualScore && r.scoreline === actualScore;
          const mv = movements?.[r.scoreline];
          return (
            <li
              key={`${r.rank}-${r.scoreline}`}
              className={`flex justify-between gap-2 rounded px-2 py-1 ${hit ? "bg-green-500/15 text-green-300" : ""}`}
            >
              <span>
                {r.rank}. {r.scoreline}
                {hit && " ✓"}
              </span>
              <span className="text-muted-foreground shrink-0">
                {title.includes("Enhanced") && mv !== undefined ? movementArrow(mv) : null}
                {r.probability != null ? ` ${(r.probability * 100).toFixed(1)}%` : ""}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default function OwnerEcseShadowLab() {
  const [summary, setSummary] = useState(null);
  const [fixtures, setFixtures] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");
  const [league, setLeague] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sum, list] = await Promise.all([
        fetchOwnerEcseShadowLabSummary(),
        fetchOwnerEcseShadowLabFixtures({
          filter,
          league: league.trim() || undefined,
          dateFrom: dateFrom || undefined,
          dateTo: dateTo || undefined,
          limit: 200,
        }),
      ]);
      setSummary(sum);
      setFixtures(list.items || []);
      setTotal(list.total ?? 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load ECSE shadow lab");
    } finally {
      setLoading(false);
    }
  }, [filter, league, dateFrom, dateTo]);

  useEffect(() => {
    load();
  }, [load]);

  const openDetail = async (fixtureId) => {
    setDetailLoading(true);
    try {
      setDetail(await fetchOwnerEcseShadowLabFixture(fixtureId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load fixture detail");
    } finally {
      setDetailLoading(false);
    }
  };

  const metrics = summary?.evaluation_metrics;
  const x3 = summary?.x3_b;

  return (
    <div className="space-y-6 pb-12">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 text-primary mb-1">
            <Beaker className="w-5 h-5" />
            <span className="text-sm font-medium uppercase tracking-wide">Owner research</span>
          </div>
          <h1 className="text-3xl font-display font-bold">ECSE Shadow Lab</h1>
          <p className="text-muted-foreground mt-1 max-w-2xl">
            Compare baseline ECSE exact-score shortlists vs M5 shortlist enhancer and X3 j2_g_slope shadow output.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 flex gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div className="text-sm">
          <strong className="text-amber-300">Owner research lab only. Not public. Does not change live predictions.</strong>
          <p className="text-muted-foreground mt-1">
            Shadow rows are collected when ECSE_X2_M6_SHADOW_LIVE_ENABLED=1. Public prediction output remains unchanged.
          </p>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{error}</div>
      )}

      {summary && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <StatCard label="Shadow rows" value={summary.total_shadow_rows} />
            <StatCard label="Enhancer applied" value={summary.applied_count} />
            <StatCard label="Excluded" value={summary.excluded_count} />
            <StatCard label="Missing ft_home odds" value={summary.missing_ft_home_count} />
            <StatCard label="Balanced excluded" value={summary.balanced_excluded_count} />
            <StatCard label="Strong home (≥60%)" value={summary.strong_home_segment_count} />
            <StatCard label="Pending evaluations" value={summary.pending_evaluations} />
            <StatCard label="Completed evaluations" value={summary.completed_evaluations} />
            <StatCard
              label="Public output changed"
              value={summary.public_output_changed_count}
              warn={summary.public_output_changed_count !== 0}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard label="Baseline Top-1/3/5/10" value={pctBlock(metrics, "top1")} sub="Top-1 hit rate" />
            <StatCard label="Enhanced Top-1" value={pctBlock(metrics, "top1")} />
            <StatCard label="Enhanced Top-3" value={pctBlock(metrics, "top3")} />
            <StatCard label="Enhanced Top-5" value={pctBlock(metrics, "top5")} />
            <StatCard label="Delta Top-10" value={pctBlock(metrics, "top10")} sub="Evaluated fixtures only" />
          </div>

          {x3 && (
            <div className="glass rounded-xl p-4 border border-violet-500/20">
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <span className="text-xs font-medium uppercase tracking-wide text-violet-300">ECSE X3 — J2/G/OU Slope</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-violet-500/20 text-violet-300 border border-violet-500/30">Shadow Only</span>
                <span className="text-xs text-muted-foreground">Not promoted</span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                <StatCard label="X3 available" value={x3.x3_available_count} />
                <StatCard label="X3 unavailable" value={x3.x3_unavailable_count} />
                <StatCard label="X3 coverage" value={`${x3.coverage_percentage ?? 0}%`} />
                <StatCard
                  label="Recommendation"
                  value={x3.candidate?.recommendation || "USE_ONLY_HI_J2_G_SLOPE"}
                  sub="research_candidate"
                />
                <StatCard
                  label="X3 vs baseline Top-1 Δ"
                  value={
                    x3.comparison_vs_baseline?.x3_delta_top1_pp != null
                      ? `${x3.comparison_vs_baseline.x3_delta_top1_pp >= 0 ? "+" : ""}${x3.comparison_vs_baseline.x3_delta_top1_pp}pp`
                      : "—"
                  }
                />
                <StatCard
                  label="M5 applied (evaluated)"
                  value={x3.comparison_vs_m5?.m5_applied_with_actual ?? "—"}
                />
              </div>
            </div>
          )}
        </>
      )}

      <div className="glass rounded-xl p-4 space-y-4">
        <div className="flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setFilter(f.value)}
              className={`px-3 py-1.5 rounded-lg text-xs border transition ${
                filter === f.value
                  ? "bg-primary/20 border-primary/50 text-primary"
                  : "border-white/10 text-muted-foreground hover:border-white/20"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-3 items-end">
          <label className="text-xs text-muted-foreground">
            League / tournament
            <input
              className="block mt-1 rounded-lg bg-black/30 border border-white/10 px-3 py-1.5 text-sm w-48"
              value={league}
              onChange={(e) => setLeague(e.target.value)}
              placeholder="Filter league…"
            />
          </label>
          <label className="text-xs text-muted-foreground">
            From
            <input
              type="date"
              className="block mt-1 rounded-lg bg-black/30 border border-white/10 px-3 py-1.5 text-sm"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </label>
          <label className="text-xs text-muted-foreground">
            To
            <input
              type="date"
              className="block mt-1 rounded-lg bg-black/30 border border-white/10 px-3 py-1.5 text-sm"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </label>
          <Button size="sm" variant="secondary" onClick={load}>
            Apply filters
          </Button>
        </div>
      </div>

      <div className="glass rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-white/10 text-sm text-muted-foreground">
          {loading ? "Loading…" : `${total} fixture(s) — showing ${fixtures.length}`}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground border-b border-white/10">
                <th className="p-3">Fixture</th>
                <th className="p-3">Kickoff</th>
                <th className="p-3">League</th>
                <th className="p-3">Home prob</th>
                <th className="p-3">Segment</th>
                <th className="p-3">Applied</th>
                <th className="p-3">Exclusion</th>
                <th className="p-3">Baseline T1</th>
                <th className="p-3">Enhanced T1</th>
                <th className="p-3">X3 T1</th>
                <th className="p-3">X3 status</th>
                <th className="p-3">Movement</th>
                <th className="p-3">Eval</th>
                <th className="p-3">Actual</th>
                <th className="p-3">B rank</th>
                <th className="p-3">E rank</th>
                <th className="p-3">Delta</th>
                <th className="p-3">Public Δ</th>
                <th className="p-3" />
              </tr>
            </thead>
            <tbody>
              {fixtures.map((row) => (
                <tr key={row.fixture_id} className="border-b border-white/5 hover:bg-white/5">
                  <td className="p-3 font-medium">{row.fixture_label || row.fixture_id}</td>
                  <td className="p-3 text-muted-foreground whitespace-nowrap">{row.kickoff_time?.slice(0, 16) || "—"}</td>
                  <td className="p-3 text-muted-foreground">{row.league || row.tournament || "—"}</td>
                  <td className="p-3">{row.home_prob != null ? `${(row.home_prob * 100).toFixed(0)}%` : "—"}</td>
                  <td className="p-3 text-xs">{row.segment_summary}</td>
                  <td className="p-3">{row.applied ? "Yes" : "No"}</td>
                  <td className="p-3 text-xs">{exclusionLabel(row.exclusion_reason)}</td>
                  <td className="p-3">{row.baseline_top1 || "—"}</td>
                  <td className="p-3">{row.enhanced_top1 || "—"}</td>
                  <td className="p-3">{row.x3_top1 || "—"}</td>
                  <td className="p-3 text-xs">{row.x3_status || "—"}</td>
                  <td className="p-3 text-xs">{row.rank_movement_summary}</td>
                  <td className="p-3">{row.evaluation_status || "—"}</td>
                  <td className="p-3">{row.actual_score || "—"}</td>
                  <td className="p-3">{row.baseline_hit_rank ?? "—"}</td>
                  <td className="p-3">{row.enhanced_hit_rank ?? "—"}</td>
                  <td className="p-3 text-xs">{deltaLabel(row)}</td>
                  <td className="p-3">{row.public_output_changed ? "Yes" : "No"}</td>
                  <td className="p-3">
                    <button
                      type="button"
                      className="text-primary hover:underline inline-flex items-center gap-1"
                      onClick={() => openDetail(row.fixture_id)}
                    >
                      Detail <ChevronRight className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && fixtures.length === 0 && (
                <tr>
                  <td colSpan={19} className="p-8 text-center text-muted-foreground">
                    No shadow rows match this filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {(detail || detailLoading) && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/60" onClick={() => !detailLoading && setDetail(null)}>
          <div
            className="w-full max-w-4xl h-full overflow-y-auto bg-background border-l border-white/10 p-6 space-y-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-start">
              <div>
                <h2 className="text-xl font-bold">{detail?.fixture_label || "Fixture detail"}</h2>
                <p className="text-sm text-muted-foreground">Fixture #{detail?.fixture_id}</p>
              </div>
              <button type="button" onClick={() => setDetail(null)} className="p-2 rounded-lg hover:bg-white/10">
                <X className="w-5 h-5" />
              </button>
            </div>

            {detailLoading && <p className="text-muted-foreground">Loading detail…</p>}

            {detail && !detailLoading && (
              <>
                <div className="rounded-xl border border-primary/30 bg-primary/5 p-4 text-sm">
                  <strong>Owner note:</strong> {detail.owner_note}
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div><span className="text-muted-foreground">Actual score</span><div>{detail.actual_score || "Pending"}</div></div>
                  <div><span className="text-muted-foreground">Baseline hit rank</span><div>{detail.baseline_hit_rank ?? "—"}</div></div>
                  <div><span className="text-muted-foreground">Enhanced hit rank</span><div>{detail.enhanced_hit_rank ?? "—"}</div></div>
                  <div><span className="text-muted-foreground">Home prob</span><div>{detail.home_prob != null ? `${(detail.home_prob * 100).toFixed(1)}%` : "—"}</div></div>
                  <div><span className="text-muted-foreground">Odds snapshot</span><div>{detail.odds_snapshot_id ?? "—"}</div></div>
                  <div><span className="text-muted-foreground">Segment</span><div>{detail.segment_summary}</div></div>
                  <div><span className="text-muted-foreground">Exclusion</span><div>{exclusionLabel(detail.exclusion_reason)}</div></div>
                  <div><span className="text-muted-foreground">Public changed</span><div>{detail.public_output_changed ? "Yes" : "No"}</div></div>
                </div>

                <div className="grid md:grid-cols-2 gap-4">
                  <Top10Panel title="Baseline ECSE Top-10" rows={detail.baseline_top10} actualScore={detail.actual_score} />
                  <Top10Panel
                    title="M5 Enhanced Shadow Top-10"
                    rows={detail.enhanced_top10}
                    actualScore={detail.actual_score}
                    movements={detail.rank_movements}
                  />
                </div>

                {detail.x3_top10 && detail.x3_status === "available" && (
                  <Top10Panel
                    title="ECSE X3 — J2/G/OU Slope (Shadow Only)"
                    rows={detail.x3_top10}
                    actualScore={detail.actual_score}
                  />
                )}

                {(detail.x3_j2 != null || detail.x3_missing_fields?.length > 0) && (
                  <div className="text-sm grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div><span className="text-muted-foreground">J2</span><div>{detail.x3_j2 ?? "—"}</div></div>
                    <div><span className="text-muted-foreground">G</span><div>{detail.x3_g ?? "—"}</div></div>
                    <div><span className="text-muted-foreground">OU slope</span><div>{detail.x3_ou_slope ?? "—"}</div></div>
                    <div><span className="text-muted-foreground">X3 vs baseline</span><div>{detail.x3_vs_baseline || "—"}</div></div>
                    {detail.x3_missing_fields?.length > 0 && (
                      <div className="col-span-2"><span className="text-muted-foreground">Missing fields</span><div>{detail.x3_missing_fields.join(", ")}</div></div>
                    )}
                  </div>
                )}

                {detail.audit_trace && (
                  <details className="text-xs">
                    <summary className="cursor-pointer text-muted-foreground">Audit trace</summary>
                    <pre className="mt-2 p-3 rounded-lg bg-black/40 overflow-x-auto">{JSON.stringify(detail.audit_trace, null, 2)}</pre>
                  </details>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
