/** Phase 37A/63 — role helpers (re-export centralized RBAC). */

export {
  normalizeRole,
  roleRank,
  hasMinimumRole,
  isOwnerUser,
  isSuperAdminUser,
  isAdminUser,
  canSeeAdminNav,
  canSeeSuperAdminNav,
  canSeeOwnerNav,
  canSeeApiSettings,
  postLoginPath,
} from "@/lib/rbac";
