/** Safe derived view-model builders for Match Detail — never throw into parent render. */

import {
  buildSummary,
  buildAiInsights,
  groupMarkets,
  buildTeamComparison,
  buildOddsCenter,
  buildXgSection,
  buildPressureSection,
  buildLineupsSection,
  buildConfidenceExplanation,
  buildAgentContribution,
} from "@/lib/predictionDetailProUtils";

export function deriveMatchDetailView(displayData, { isOwner = false } = {}) {
  if (!displayData) {
    return {
      summary: null,
      insights: [],
      marketGroups: [],
      teamMetrics: [],
      odds: null,
      xg: null,
      pressure: null,
      lineups: null,
      confidenceExpl: null,
      agents: [],
      deriveError: null,
    };
  }
  try {
    return {
      summary: buildSummary(displayData, { isOwner }),
      insights: buildAiInsights(displayData),
      marketGroups: groupMarkets(displayData, { isOwner }),
      teamMetrics: buildTeamComparison(displayData),
      odds: buildOddsCenter(displayData),
      xg: buildXgSection(displayData),
      pressure: buildPressureSection(displayData),
      lineups: buildLineupsSection(displayData),
      confidenceExpl: buildConfidenceExplanation(displayData),
      agents: buildAgentContribution(displayData),
      deriveError: null,
    };
  } catch (err) {
    console.error("[deriveMatchDetailView] failed", err);
    return {
      summary: null,
      insights: [],
      marketGroups: [],
      teamMetrics: [],
      odds: null,
      xg: null,
      pressure: null,
      lineups: null,
      confidenceExpl: null,
      agents: [],
      deriveError: err instanceof Error ? err.message : String(err),
    };
  }
}
