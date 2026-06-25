/** User-facing checkout error messages keyed by API error code. */

export const CHECKOUT_INACTIVE_MSG = "Payment checkout is not active yet.";
export const PLAN_UNAVAILABLE_MSG = "This plan is not available yet.";

const CODE_MESSAGES = {
  checkout_disabled: CHECKOUT_INACTIVE_MSG,
  stripe_not_configured: CHECKOUT_INACTIVE_MSG,
  price_not_configured: PLAN_UNAVAILABLE_MSG,
  stripe_price_invalid: PLAN_UNAVAILABLE_MSG,
  unknown_plan: PLAN_UNAVAILABLE_MSG,
  stripe_checkout_failed: "Could not start checkout. Please try again or contact support.",
  duplicate_active_plan: "You already have an active subscription for this plan.",
  invalid_upgrade: "Cannot checkout for the same or lower plan tier.",
  checkout_rate_limited: "Too many checkout attempts. Please try again later.",
  email_verification_required: "Email verification required before checkout.",
  account_blocked: "Account is not allowed.",
};

export function checkoutErrorMessage(err, fallback = "Checkout unavailable") {
  if (!err) return fallback;
  const code = err?.code;
  if (code && CODE_MESSAGES[code]) return CODE_MESSAGES[code];
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}
