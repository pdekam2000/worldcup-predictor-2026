/** Phase 39A — canonical SaaS pricing plans (FREE / STARTER / PRO). */

export const PLAN_RANK = { free: 0, starter: 1, pro: 2 };

/** Normalize legacy/admin plan keys to canonical SaaS tiers. */
export function normalizePlanKey(plan) {
  const key = String(plan || "free").trim().toLowerCase();
  if (key === "elite" || key === "unlimited" || key === "premium") return "pro";
  if (key in PLAN_RANK) return key;
  return "free";
}

export function planRank(plan) {
  return PLAN_RANK[normalizePlanKey(plan)] ?? 0;
}

/** True when the user may start checkout for `targetPlan`. */
export function canUpgradeTo(currentPlan, targetPlan) {
  return planRank(targetPlan) > planRank(currentPlan);
}

export function isPremiumPlan(plan) {
  return normalizePlanKey(plan) === "pro";
}

export const PRICING_PLANS = [
  {
    key: "free",
    name: "Free",
    price: 0,
    monthlyPredictions: 4,
    recommended: false,
    markets: ["1X2"],
    features: ["4 predictions per month", "1X2 only", "Basic access"],
  },
  {
    key: "starter",
    name: "Starter",
    price: 5,
    monthlyPredictions: 28,
    recommended: true,
    markets: ["1X2", "BTTS", "Over/Under"],
    features: [
      "28 predictions per month",
      "1X2 + BTTS + Over/Under",
      "Full prediction history",
      "Ranked picks",
    ],
  },
  {
    key: "pro",
    name: "Pro",
    price: 19,
    monthlyPredictions: 60,
    recommended: false,
    markets: ["All markets"],
    features: [
      "60 predictions per month",
      "All prediction markets",
      "Goal Minute (future)",
      "First Goal Team / Scorer (future)",
      "xG Premium Markets (future)",
      "Priority support",
    ],
  },
];

export const COMPARISON_ROWS = [
  { label: "Price", free: "€0", starter: "€5/mo", pro: "€19/mo" },
  { label: "Predictions / month", free: "4", starter: "28", pro: "60" },
  { label: "1X2", free: true, starter: true, pro: true },
  { label: "BTTS", free: false, starter: true, pro: true },
  { label: "Over/Under", free: false, starter: true, pro: true },
  { label: "Best picks", free: false, starter: true, pro: true },
  { label: "Archive access", free: "Limited", starter: true, pro: true },
  { label: "Analytics center", free: true, starter: true, pro: true },
  { label: "Goal Minute", free: false, starter: false, pro: "Future" },
  { label: "First Goal Team", free: false, starter: false, pro: "Future" },
  { label: "First Goal Scorer", free: false, starter: false, pro: "Future" },
  { label: "xG Premium Markets", free: false, starter: false, pro: "Future" },
  { label: "Premium Markets", free: false, starter: false, pro: true },
];

/** Elite exists in backend enums but is not a self-serve checkout tier yet. */
export const ELITE_PLAN_COMING_SOON = {
  key: "elite",
  name: "Elite",
  price: null,
  comingSoon: true,
  description: "Extended premium tier for power users — not available for self-serve checkout yet.",
  features: [
    "All Pro markets",
    "Priority roadmap access",
    "Coming soon",
  ],
};

export function isLegacyElitePlan(plan) {
  const key = String(plan || "").trim().toLowerCase();
  return key === "elite" || key === "unlimited" || key === "premium";
}

export function displayPlanLabel(plan) {
  const key = String(plan || "free").trim().toLowerCase();
  if (isLegacyElitePlan(key)) return "Pro (legacy Elite)";
  const match = PRICING_PLANS.find((p) => p.key === normalizePlanKey(key));
  return match?.name || "Free";
}

export const CONTACT_CATEGORIES = [
  { value: "support", label: "Support" },
  { value: "subscription", label: "Subscription" },
  { value: "billing", label: "Billing" },
  { value: "prediction_issue", label: "Prediction Issue" },
  { value: "feature_request", label: "Feature Request" },
  { value: "other", label: "Other" },
];
