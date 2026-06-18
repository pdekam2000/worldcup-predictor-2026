import { useEffect } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/AuthContext";
import { isDevAuthBypass } from "@/lib/devAuth";

const DefaultFallback = () => (
  <div className="fixed inset-0 flex items-center justify-center">
    <div className="w-8 h-8 border-4 border-slate-200 border-t-slate-800 rounded-full animate-spin"></div>
  </div>
);

export default function ProtectedRoute({ fallback = <DefaultFallback />, unauthenticatedElement }) {
  const { isAuthenticated, isLoadingAuth, authChecked, checkUserAuth } = useAuth();
  const navigate = useNavigate();
  const bypass = isDevAuthBypass();

  useEffect(() => {
    if (bypass) return;
    if (!authChecked && !isLoadingAuth) {
      checkUserAuth();
    }
  }, [bypass, authChecked, isLoadingAuth, checkUserAuth]);

  if (bypass) {
    return <Outlet />;
  }

  if (isLoadingAuth || !authChecked) {
    return fallback;
  }

  if (!isAuthenticated) {
    if (unauthenticatedElement) {
      return unauthenticatedElement;
    }
    navigate("/login", { replace: true });
    return null;
  }

  return <Outlet />;
}
