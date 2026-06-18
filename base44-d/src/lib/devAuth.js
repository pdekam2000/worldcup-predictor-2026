/** Temporary dev-only auth bypass — never enable in production builds intentionally. */

export const DEV_MOCK_USER = {
  email: "dev@worldcup.local",
  full_name: "Dev User",
  role: "admin",
};

export function isDevAuthBypass() {
  return import.meta.env.VITE_DEV_AUTH_BYPASS === "true";
}
