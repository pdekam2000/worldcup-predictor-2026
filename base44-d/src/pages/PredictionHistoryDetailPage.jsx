import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Trophy,
  RefreshCw,
  AlertCircle,
  ShieldAlert,
  Calendar,
  Target,
  Database,
} from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { isAdminUser, isOwnerUser } from "@/lib/roles";
import { fetchPredictionHistoryEntry } from "@/api/saasApi";
import { Button } from "@/components/ui/button";
import { getArchiveStatusConfig, resolveArchiveStatus } from "@/lib/archiveStatus";
import ArchiveSection, { MarketResultRow, JsonBlock } from "@/components/archive/ArchiveDetailSections";
import MatchTeamsRow from "@/components/match/MatchTeamsRow";

function formatDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return "—";
  }
}

const EVAL_SOURCE_LABELS = {
  worldcup_prediction_evaluations: "Production evaluation table",
  stored_snapshot: "Stored prediction snapshot",
  fixture_resolver: "Fixture outcome resolver",
};

function AgentSummaryBlock({ agentSummary }) {
  if (!agentSummary?.available || !agentSummary?.specialist_summary) {
    return (
      <p className="text-sm text-muted-foreground">
        No agent summary stored for this prediction snapshot.
      </p>
    );
  }

  const summary = agentSummary.specialist_summary;
  const agents = summary.agents || {};
  const entries = Object.entries(agents);

  return (
    <div className="space-y-3">
      {summary.aggregated_score != null && (
        <p className="text-sm">
          Aggregated specialist score:{" "}
          <span className="font-semibold tabular-nums">
            {Math.round(Number(summary.aggregated_score) * 1000) / 10}%
          </span>
        </p>
      )}
      {agentSummary.agent_count != null && (
        <p className="text-xs text-muted-foreground">Agents recorded: {agentSummary.agent_count}</p>
      )}
      {entries.length > 0 ? (
        <div className="space-y-2">
          {entries.map(([name, block]) => (
            <div key={name} className="rounded-lg border border-border bg-muted/40 p-3 text-sm">
              <div className="font-medium capitalize">{name.replace(/_/g, " ")}</div>
              {block?.status && (
                <div className="text-xs text-muted-foreground mt-1">Status: {block.status}</div>
              )}
              {block?.signal != null && (
                <div className="text-xs text-muted-foreground">Signal: {String(block.signal)}</div>
              )}
              {block?.reason && <div className="text-xs mt-1">{block.reason}</div>}
            </div>
          ))}
        </div>
      ) : (
        <JsonBlock data={summary} />
      )}
    </div>
  );
}

function ConfidenceTraceBlock({ confidenceTrace }) {
  if (!confidenceTrace?.available) {
    return (
      <p className="text-sm text-muted-foreground">
        No confidence trace stored for this prediction snapshot.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {confidenceTrace.adaptive_confidence_trace && (
        <div>
          <p className="text-xs text-muted-foreground mb-2">Adaptive confidence trace</p>
          <JsonBlock data={confidenceTrace.adaptive_confidence_trace} />
        </div>
      )}
      {confidenceTrace.rule_a_gate && (
        <div>
          <p className="text-xs text-muted-foreground mb-2">Rule A gate</p>
          <JsonBlock data={confidenceTrace.rule_a_gate} />
        </div>
      )}
    </div>
  );
}

function ExplanationBlock({ explanation }) {
  if (!explanation?.available) {
    return (
      <p className="text-sm text-muted-foreground">
        No prediction explanation stored in the archive snapshot.
      </p>
    );
  }

  if (explanation.reasoning && typeof explanation.reasoning === "string") {
    return <p className="text-sm leading-relaxed">{explanation.reasoning}</p>;
  }

  return (
    <div className="space-y-3">
      {explanation.harmonization && (
        <div>
          <p className="text-xs text-muted-foreground mb-2">Harmonization</p>
          <JsonBlock data={explanation.harmonization} />
        </div>
      )}
      {explanation.audit_trace && (
        <div>
          <p className="text-xs text-muted-foreground mb-2">Audit trace</p>
          <JsonBlock data={explanation.audit_trace} />
        </div>
      )}
    </div>
  );
}

export default function PredictionHistoryDetailPage() {
  const { entryId, predictionId } = useParams();
  const id = entryId || predictionId;
  const { user } = useAuth();
  const isAdmin = isAdminUser(user);
  const isOwner = isOwnerUser(user);
  const showDebug = isAdmin || isOwner;
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPredictionHistoryEntry(id);
      setDetail(data);
    } catch (err) {
      setDetail(null);
      setError(err instanceof Error ? err.message : "Failed to load archive entry");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const summaryStatus = resolveArchiveStatus({
    ...detail?.evaluation,
    ...detail?.summary,
    market_statuses: detail?.evaluation?.market_statuses,
    evaluated_markets_count: detail?.evaluation?.evaluated_markets_count,
    correct_markets_count: detail?.evaluation?.correct_markets_count,
    wrong_markets_count: detail?.evaluation?.wrong_markets_count,
  });
  const summaryCfg = getArchiveStatusConfig(summaryStatus);
  const SummaryIcon = summaryCfg.icon;
  const evaluation = detail?.evaluation || {};
  const evalSource = detail?.evaluation_source || {};

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Link
          to="/archive"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-primary transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Archive
        </Link>
        <Button variant="outline" size="sm" onClick={load} disabled={loading} className="gap-2">
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
        </div>
      ) : error ? (
        <div className="glass rounded-xl p-8 border border-red-200 text-center space-y-3">
          <AlertCircle className="w-10 h-10 text-red-500 mx-auto" />
          <p className="text-red-700">{error}</p>
          <Button variant="secondary" onClick={load}>
            Retry
          </Button>
        </div>
      ) : detail ? (
        <>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className={`rounded-2xl border p-6 ${summaryCfg.card}`}
          >
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="space-y-4 min-w-0 flex-1">
                {detail.home_team && detail.away_team && (
                  <MatchTeamsRow
                    homeTeam={detail.home_team}
                    awayTeam={detail.away_team}
                    countryHint={detail.competition}
                    size="md"
                    className="max-w-md"
                  />
                )}
                <h1 className="text-2xl font-display font-bold truncate sr-only">{detail.match_name}</h1>
                <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                  <span className="inline-flex items-center gap-1.5">
                    <Trophy className="w-4 h-4" />
                    {detail.competition}
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <Calendar className="w-4 h-4" />
                    Match: {formatDate(detail.match_date)}
                  </span>
                  <span>Predicted: {formatDate(detail.prediction_date)}</span>
                </div>
              </div>
              <span
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold shrink-0 ${summaryCfg.badge}`}
              >
                <SummaryIcon className="w-4 h-4" />
                {summaryCfg.label}
              </span>
            </div>

            <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              <div>
                <div className="text-xs text-muted-foreground">Main prediction</div>
                <div className="font-semibold mt-1 flex items-center gap-1.5">
                  <Target className="w-4 h-4 text-primary" />
                  {detail.summary?.main_prediction_label || "—"}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Confidence</div>
                <div className="font-semibold mt-1 tabular-nums">
                  {detail.summary?.confidence != null
                    ? `${Math.round(Number(detail.summary.confidence))}%`
                    : "—"}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Final score</div>
                <div className="font-semibold mt-1">{evaluation.final_score || "—"}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Actual winner</div>
                <div className="font-semibold mt-1">{evaluation.actual_result_label || "—"}</div>
              </div>
            </div>

            {detail.fixture_id && (
              <div className="mt-4 pt-4 border-t border-white/10">
                <Link to={`/prediction/${detail.fixture_id}`} className="text-sm text-primary hover:underline">
                  Open live prediction page for this fixture
                </Link>
              </div>
            )}
          </motion.div>

          <ArchiveSection title="Evaluation result" description="How this prediction was scored">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-xs text-muted-foreground">Source</div>
                <div className="font-medium mt-1 flex items-center gap-1.5">
                  <Database className="w-3.5 h-3.5 text-muted-foreground" />
                  {EVAL_SOURCE_LABELS[evalSource.source] || evalSource.source || "—"}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Evaluated at</div>
                <div className="font-medium mt-1">{formatDate(evalSource.evaluated_at || evaluation.evaluated_at)}</div>
              </div>
              {evalSource.row_status_reason && (
                <div className="sm:col-span-2">
                  <div className="text-xs text-muted-foreground">Status reason</div>
                  <div className="font-medium mt-1 text-muted-foreground">{evalSource.row_status_reason}</div>
                </div>
              )}
              {showDebug && evalSource.is_quarantined && (
                <div className="sm:col-span-2 text-xs text-yellow-200/90">
                  This evaluation row is quarantined and excluded from public accuracy metrics.
                </div>
              )}
            </div>
          </ArchiveSection>

          <ArchiveSection title="Market breakdown" description="Per-market picks and results">
            {!detail.prediction?.detailed_markets_available && (
              <p className="text-sm text-muted-foreground">
                Full market snapshot unavailable — showing history record only.
              </p>
            )}
            <div className="space-y-3">
              {(detail.prediction?.markets || []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No market rows available for this entry.</p>
              ) : (
                (detail.prediction?.markets || []).map((market) => (
                  <MarketResultRow key={market.key} market={market} />
                ))
              )}
            </div>
          </ArchiveSection>

          <ArchiveSection
            title="Prediction explanation"
            description="Stored reasoning from the prediction snapshot"
            defaultOpen={Boolean(detail.prediction_explanation?.available)}
          >
            <ExplanationBlock explanation={detail.prediction_explanation} />
          </ArchiveSection>

          <ArchiveSection
            title="Agent summary"
            description="Specialist agent signals when stored"
            defaultOpen={Boolean(detail.agent_summary?.available)}
          >
            <AgentSummaryBlock agentSummary={detail.agent_summary} />
          </ArchiveSection>

          <ArchiveSection
            title="Confidence trace"
            description="Adaptive confidence and Rule A metadata"
            defaultOpen={Boolean(detail.confidence_trace?.available)}
          >
            <ConfidenceTraceBlock confidenceTrace={detail.confidence_trace} />
          </ArchiveSection>

          {detail.consistency?.available && (
            <ArchiveSection title="Consistency guard" defaultOpen={false}>
              <div className="flex items-start gap-2 text-sm">
                <ShieldAlert className="w-5 h-5 text-yellow-400 shrink-0 mt-0.5" />
                <div className="space-y-2">
                  {(detail.consistency.withheld_markets || []).length > 0 && (
                    <p>
                      <span className="text-muted-foreground">Withheld markets: </span>
                      {detail.consistency.withheld_markets.join(", ")}
                    </p>
                  )}
                  {(detail.consistency.consistency_warnings || []).length > 0 && (
                    <ul className="text-yellow-200/90 space-y-1 list-disc list-inside">
                      {detail.consistency.consistency_warnings.map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </ArchiveSection>
          )}

          {showDebug && (
            <ArchiveSection title="Owner / Admin debug" description="Engine trace — hidden from public users" defaultOpen={false}>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm mb-3">
                <div>
                  <div className="text-xs text-muted-foreground">Engine version</div>
                  <div className="font-medium mt-0.5">{detail.metadata?.prediction_engine_version || "—"}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Generated at</div>
                  <div className="font-medium mt-0.5">{formatDate(detail.metadata?.generated_at)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Snapshot source</div>
                  <div className="font-medium mt-0.5">{detail.metadata?.snapshot_source || "—"}</div>
                </div>
              </div>
              <JsonBlock data={detail} />
            </ArchiveSection>
          )}
        </>
      ) : null}
    </div>
  );
}
