/** Dev-only auth bypass — disabled in production builds regardless of env flag. */

export const DEV_MOCK_USER = {
  email: "dev@worldcup.local",
  full_name: "Dev User",
  role: "user",
};

export function isDevAuthBypass() {
  return import.meta.env.DEV && import.meta.env.VITE_DEV_AUTH_BYPASS === "true";
}
