/** Safe percent / confidence display — avoids double-scaling (81 → 81%, not 8100%). */

export function formatPercent(value, { digits = 1, fallback = "—" } = {}) {
  if (value == null || value === "") return fallback;
  const n = Number(value);
  if (Number.isNaN(n)) return fallback;
  const pct = n <= 1 && n >= -1 ? n * 100 : n;
  if (Number.isNaN(pct)) return fallback;
  return `${pct.toFixed(digits)}%`;
}

export function formatRatio(value, { digits = 1, fallback = "—" } = {}) {
  if (value == null || value === "") return fallback;
  const n = Number(value);
  if (Number.isNaN(n)) return fallback;
  if (n <= 1 && n >= 0) return formatPercent(n, { digits, fallback });
  return `${n.toFixed(digits)}%`;
}

export function formatGoalTimingRange(value, { confidence = null } = {}) {
  if (value == null || value === "") {
    if (confidence == null) return "Pending";
    return "N/A";
  }
  const text = String(value).trim();
  if (!text || text.toLowerCase() === "nan" || text.includes("NaN")) {
    return confidence == null ? "Pending" : "Unknown";
  }
  if (text.toLowerCase() === "pending") return "Pending";
  if (text.toLowerCase() === "unknown") return "Unknown";
  return text;
}

export function formatPickWithProb(pred) {
  if (pred == null) return "—";
  if (typeof pred === "object" && !Array.isArray(pred)) {
    const entries = Object.entries(pred).filter(([, v]) => v != null && !Number.isNaN(Number(v)));
    if (!entries.length) return "—";
    const top = entries.sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))[0];
    const prob = Number(top[1]);
    if (!Number.isNaN(prob) && prob > 0) {
      return `${top[0]} (${formatPercent(prob)})`;
    }
    return String(top[0]);
  }
  if (Array.isArray(pred)) return pred.length ? pred.join(", ") : "—";
  const s = String(pred);
  if (s.toLowerCase() === "nan") return "Unknown";
  return s || "—";
}
