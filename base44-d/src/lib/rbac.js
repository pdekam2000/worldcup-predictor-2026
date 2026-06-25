/** Phase 63 — centralized RBAC helpers (frontend). */

const ROLE_RANK = {
  guest: 0,
  free_user: 10,
  user: 10,
  starter: 20,
  pro: 30,
  premium: 40,
  admin: 50,
  super_admin: 60,
  owner: 100,
};

export function normalizeRole(role) {
  const raw = String(role || "guest").toLowerCase();
  if (raw === "user") return "free_user";
  return ROLE_RANK[raw] != null ? raw : "guest";
}

export function roleRank(role) {
  return ROLE_RANK[normalizeRole(role)] ?? 0;
}

export function hasMinimumRole(user, minimum) {
  return roleRank(user?.role) >= roleRank(minimum);
}

export function isOwnerUser(user) {
  return normalizeRole(user?.role) === "owner";
}

export function isSuperAdminUser(user) {
  const r = normalizeRole(user?.role);
  return r === "super_admin" || r === "owner";
}

export function isAdminUser(user) {
  return roleRank(user?.role) >= ROLE_RANK.admin;
}

export function canSeeAdminNav(user) {
  return isAdminUser(user) && !isOwnerUser(user);
}

export function canSeeSuperAdminNav(user) {
  return isSuperAdminUser(user) && !isOwnerUser(user);
}

export function canSeeOwnerNav(user) {
  return isOwnerUser(user);
}

export function canSeeApiSettings(user) {
  return isAdminUser(user);
}

export function postLoginPath(user) {
  if (isOwnerUser(user)) return "/owner";
  return "/dashboard";
}
