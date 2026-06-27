/**
 * Plan-based UI gating helpers — Phase A15 (display only, no billing changes).
 */

const PLAN_RANK = { free: 0, starter: 1, pro: 2, enterprise: 3 };

export function normalizePlan(subscription) {
  const raw = String(subscription?.plan || subscription?.plan_name || "free").toLowerCase();
  if (raw.includes("pro") || raw.includes("elite")) return "pro";
  if (raw.includes("starter") || raw.includes("basic")) return "starter";
  if (raw.includes("enterprise")) return "enterprise";
  return "free";
}

export function planRank(plan) {
  return PLAN_RANK[normalizePlan({ plan })] ?? 0;
}

export function canViewCoreMarkets(subscription) {
  return planRank(normalizePlan(subscription)) >= PLAN_RANK.starter;
}

export function canViewCombos(subscription) {
  return planRank(normalizePlan(subscription)) >= PLAN_RANK.starter;
}

export function canViewArchiveBasics(subscription) {
  return planRank(normalizePlan(subscription)) >= PLAN_RANK.starter;
}

export function canViewEgieDetail(subscription) {
  return planRank(normalizePlan(subscription)) >= PLAN_RANK.pro;
}

export function canViewModelSource(subscription) {
  return planRank(normalizePlan(subscription)) >= PLAN_RANK.pro;
}

export function canViewTierComparison(subscription) {
  return planRank(normalizePlan(subscription)) >= PLAN_RANK.pro;
}

export function canViewConfidenceTimeline(subscription) {
  return planRank(normalizePlan(subscription)) >= PLAN_RANK.pro;
}

export function canViewAgentContributions(subscription) {
  return planRank(normalizePlan(subscription)) >= PLAN_RANK.pro;
}

export function canViewFullArchive(subscription) {
  return planRank(normalizePlan(subscription)) >= PLAN_RANK.pro;
}

/** Free tier: best pick only, limited matches, hide reasoning/EGIE/tier debug */
export function gateMatchDetailPayload(payload, subscription) {
  if (!payload) return payload;
  const plan = normalizePlan(subscription);
  if (plan !== "free") return payload;
  const out = { ...payload };
  delete out.audit_trace;
  delete out.agent_contributions;
  delete out.tier_a_prediction;
  delete out.tier_b_prediction;
  if (out.markets && typeof out.markets === "object") {
    const gated = {};
    for (const [k, v] of Object.entries(out.markets)) {
      if (k === "1x2" || k === "match_winner") {
        gated[k] = {
          market_status: v?.market_status,
          final_selected_prediction: v?.final_selected_prediction,
        };
      }
    }
    out.markets = gated;
  }
  delete out.goal_timing;
  delete out.egie;
  return out;
}

export function canViewBetQualityInputs(subscription) {
  return planRank(normalizePlan(subscription)) >= PLAN_RANK.pro;
}

export function canViewCoreMarketQuality(subscription) {
  return planRank(normalizePlan(subscription)) >= PLAN_RANK.starter;
}

/** Free tier: best pick + quality tier only */
export function gatePublicationOverlay(overlay, subscription) {
  if (!overlay) return overlay;
  const plan = normalizePlan(subscription);
  if (planRank(plan) >= PLAN_RANK.pro) return overlay;
  const out = { ...overlay };
  if (plan === "starter") {
    const mq = {};
    for (const [k, v] of Object.entries(out.market_quality || {})) {
      mq[k] = { ...v };
      delete mq[k].score_inputs;
    }
    out.market_quality = mq;
    return out;
  }
  delete out.market_quality;
  return out;
}
