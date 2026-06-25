import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/lib/AuthContext";
import { isOwnerUser } from "@/lib/roles";
import AccessDenied from "@/components/AccessDenied";

/** Owner-only route guard — Phase 63 */
export default function OwnerRoute() {
  const { isAuthenticated, user, isLoadingAuth } = useAuth();

  if (isLoadingAuth) {
    return (
      <div className="flex justify-center py-20">
        <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/owner-login" replace />;
  }

  if (!isOwnerUser(user)) {
    return <AccessDenied />;
  }

  return <Outlet />;
}
