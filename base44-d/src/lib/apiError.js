/** Map API errors to user-friendly messages. */

export function extractApiErrorMessage(payload, status) {
  const detail = payload?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (detail && typeof detail === "object") {
    if (typeof detail.message === "string" && detail.message.trim()) {
      return detail.message;
    }
    if (typeof detail.code === "string") {
      return detail.message || detail.code;
    }
  }
  if (typeof payload?.message === "string" && payload.message.trim()) {
    return payload.message;
  }
  if (status === 401) return "Login required. Please sign in to continue.";
  if (status === 403) return "Permission required. You do not have access to this resource.";
  if (status === 404) return "Data not available yet.";
  if (status >= 500) return "Server error. Please try again shortly.";
  return `Request failed (${status})`;
}

export function classifyApiError(err, status) {
  const message = err?.message || "";
  if (status === 401 || /login required|authentication required/i.test(message)) {
    return { type: "auth_required", message: "Login required. Please sign in to continue." };
  }
  if (status === 403 || /access denied|permission required/i.test(message)) {
    return { type: "forbidden", message: message || "Permission required." };
  }
  if (status === 404 || /not available/i.test(message)) {
    return { type: "not_found", message: message || "Data not available yet." };
  }
  if (status >= 500) {
    return { type: "server_error", message: message || "Server error. Please try again." };
  }
  return { type: "error", message: message || "Something went wrong." };
}
