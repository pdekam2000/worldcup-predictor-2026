import { CheckCircle, XCircle, Clock, HelpCircle } from "lucide-react";

/** Shared archive evaluation status styling — yellow/white public theme. */
export const ARCHIVE_STATUS = {
  correct: {
    icon: CheckCircle,
    label: "Correct",
    card: "bg-emerald-50 border-emerald-200",
    badge: "bg-emerald-100 text-emerald-800 border border-emerald-300",
    dot: "bg-emerald-500",
  },
  wrong: {
    icon: XCircle,
    label: "Wrong",
    card: "bg-red-50 border-red-200",
    badge: "bg-red-100 text-red-800 border border-red-300",
    dot: "bg-red-500",
  },
  incorrect: {
    icon: XCircle,
    label: "Wrong",
    card: "bg-red-50 border-red-200",
    badge: "bg-red-100 text-red-800 border border-red-300",
    dot: "bg-red-500",
  },
  partial: {
    icon: HelpCircle,
    label: "Partial",
    card: "bg-violet-50 border-violet-200",
    badge: "bg-violet-100 text-violet-800 border border-violet-300",
    dot: "bg-violet-500",
  },
  pending: {
    icon: Clock,
    label: "Pending",
    card: "bg-amber-50 border-amber-200",
    badge: "bg-amber-100 text-amber-900 border border-amber-300",
    dot: "bg-amber-500",
  },
  unknown: {
    icon: HelpCircle,
    label: "Unknown",
    card: "bg-white border-slate-200",
    badge: "bg-slate-100 text-slate-600 border border-slate-200",
    dot: "bg-slate-400",
  },
  unavailable: {
    icon: HelpCircle,
    label: "Unavailable",
    card: "bg-white border-slate-200",
    badge: "bg-slate-100 text-slate-500 border border-slate-200",
    dot: "bg-slate-300",
  },
};

function normalizeStatusKey(raw) {
  const key = String(raw || "").toLowerCase().trim();
  if (key === "incorrect") return "wrong";
  if (ARCHIVE_STATUS[key]) return key;
  return null;
}

/**
 * Resolve display status from API row fields only — never fabricate results.
 * Uses result_status, evaluation_status, market_statuses, and market counts.
 */
export function resolveArchiveStatus(item) {
  if (!item) return "pending";

  const direct = normalizeStatusKey(
    item.result_status || item.evaluation_status
  );
  if (direct && direct !== "pending") return direct;

  const markets = item.market_statuses;
  if (markets && typeof markets === "object") {
    const main = normalizeStatusKey(markets["1x2"] || markets["1X2"]);
    if (main && main !== "pending") return main;
  }

  const evaluated = Number(item.evaluated_markets_count) || 0;
  const correct = Number(item.correct_markets_count) || 0;
  const wrong = Number(item.wrong_markets_count) || 0;
  if (evaluated > 0) {
    if (correct > 0 && wrong > 0) return "partial";
    if (wrong > 0 && correct === 0) return "wrong";
    if (correct > 0 && wrong === 0) return "correct";
  }

  const legacy = normalizeStatusKey(item.result);
  if (legacy && legacy !== "pending") return legacy;

  if (direct) return direct;
  return "pending";
}

export function getArchiveStatusConfig(status) {
  const key = String(status || "pending").toLowerCase();
  return ARCHIVE_STATUS[key] || ARCHIVE_STATUS.pending;
}

export function formatPct(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const num = Number(value);
  if (num <= 1) return `${Math.round(num * 1000) / 10}%`;
  return `${Math.round(num * 10) / 10}%`;
}

export function pick1x2Label(value) {
  const v = String(value || "").toLowerCase();
  if (v === "home" || v === "home_win") return "1";
  if (v === "draw") return "X";
  if (v === "away" || v === "away_win") return "2";
  return value || "—";
}

export function formatShortDate(value) {
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
