import { CheckCircle, XCircle, Clock, HelpCircle } from "lucide-react";

/** Shared archive evaluation status styling — terminal dark theme. */
export const ARCHIVE_STATUS = {
  correct: {
    icon: CheckCircle,
    label: "Correct",
    card: "bg-[#00E676]/5 border-[#00E676]/25",
    badge: "bg-[#00E676]/15 text-[#00E676] border border-[#00E676]/35",
    dot: "bg-[#00E676]",
  },
  wrong: {
    icon: XCircle,
    label: "Wrong",
    card: "bg-[#FF4D4D]/5 border-[#FF4D4D]/25",
    badge: "bg-[#FF4D4D]/15 text-[#FF4D4D] border border-[#FF4D4D]/35",
    dot: "bg-[#FF4D4D]",
  },
  incorrect: {
    icon: XCircle,
    label: "Wrong",
    card: "bg-[#FF4D4D]/5 border-[#FF4D4D]/25",
    badge: "bg-[#FF4D4D]/15 text-[#FF4D4D] border border-[#FF4D4D]/35",
    dot: "bg-[#FF4D4D]",
  },
  partial: {
    icon: HelpCircle,
    label: "Partial",
    card: "bg-violet-500/5 border-violet-500/25",
    badge: "bg-violet-500/15 text-violet-300 border border-violet-500/35",
    dot: "bg-violet-400",
  },
  pending: {
    icon: Clock,
    label: "Pending",
    card: "bg-[#FFD166]/5 border-[#FFD166]/20",
    badge: "bg-[#FFD166]/15 text-[#FFD166] border border-[#FFD166]/30",
    dot: "bg-[#FFD166]",
  },
  unknown: {
    icon: HelpCircle,
    label: "Unknown",
    card: "bg-white/[0.02] border-white/10",
    badge: "bg-white/5 text-[#94A3B8] border border-white/10",
    dot: "bg-[#94A3B8]",
  },
  unavailable: {
    icon: HelpCircle,
    label: "Unavailable",
    card: "bg-white/[0.02] border-white/10",
    badge: "bg-white/5 text-[#94A3B8] border border-white/10",
    dot: "bg-[#94A3B8]",
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
