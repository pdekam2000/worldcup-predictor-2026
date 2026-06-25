import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/lib/AuthContext";
import { isOwnerUser } from "@/lib/roles";

/** Redirect owners away from user dashboard to /owner */
export default function OwnerDashboardGate() {
  const { user } = useAuth();
  if (isOwnerUser(user)) {
    return <Navigate to="/owner" replace />;
  }
  return <Outlet />;
}
