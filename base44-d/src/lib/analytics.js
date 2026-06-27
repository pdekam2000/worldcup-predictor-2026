/** Phase 64 — lightweight product analytics (consent-aware, no third-party yet). */

const STORAGE_KEY = "wcp_analytics_events";
const MAX_EVENTS = 200;

function consentAllowsTracking() {
  const c = localStorage.getItem("cookie_consent");
  return c !== "declined";
}

export function trackEvent(name, props = {}) {
  if (!consentAllowsTracking()) return;
  try {
    const events = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    events.push({ name, props, ts: new Date().toISOString() });
    while (events.length > MAX_EVENTS) events.shift();
    localStorage.setItem(STORAGE_KEY, JSON.stringify(events));
  } catch {
    /* ignore quota errors */
  }
  if (import.meta.env.DEV) {
    console.debug("[analytics]", name, props);
  }
}

export function trackPageView(path) {
  trackEvent("page_view", { path });
}

export function initAnalyticsFromConsent() {
  trackEvent("consent_accepted");
}

export function getStoredAnalyticsEvents() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}
