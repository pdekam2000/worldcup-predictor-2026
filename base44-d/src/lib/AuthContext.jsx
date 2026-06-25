import React, { createContext, useState, useContext, useEffect, useCallback } from "react";
import { clearAuthToken,
  fetchMe,
  getAuthToken,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
} from "@/api/authApi";
import { clearAdminGateTokens } from "@/lib/adminGate";
import { DEV_MOCK_USER, isDevAuthBypass } from "@/lib/devAuth";

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoadingAuth, setIsLoadingAuth] = useState(true);
  const [authError, setAuthError] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  const checkUserAuth = useCallback(async () => {
    if (isDevAuthBypass()) {
      setUser(DEV_MOCK_USER);
      setIsAuthenticated(true);
      setIsLoadingAuth(false);
      setAuthChecked(true);
      setAuthError(null);
      return;
    }

    setIsLoadingAuth(true);
    setAuthError(null);

    if (!getAuthToken()) {
      setUser(null);
      setIsAuthenticated(false);
      setIsLoadingAuth(false);
      setAuthChecked(true);
      return;
    }

    try {
      const payload = await fetchMe();
      const currentUser = payload?.user;
      if (!currentUser) {
        throw new Error("Invalid session");
      }
      setUser(currentUser);
      setIsAuthenticated(true);
      setAuthError(null);
    } catch {
      clearAuthToken();
      setUser(null);
      setIsAuthenticated(false);
      setAuthError({ type: "auth_required", message: "Authentication required" });
    } finally {
      setIsLoadingAuth(false);
      setAuthChecked(true);
    }
  }, []);

  useEffect(() => {
    checkUserAuth();
  }, [checkUserAuth]);

  const login = async (email, password) => {
    const payload = await apiLogin(email, password);
    setUser(payload.user);
    setIsAuthenticated(true);
    setAuthError(null);
    setAuthChecked(true);
    return payload;
  };

  const register = async (email, password, inviteCode = null) => {
    const payload = await apiRegister(email, password, inviteCode);
    if (payload?.access_token && payload?.user) {
      setUser(payload.user);
      setIsAuthenticated(true);
    } else {
      setUser(null);
      setIsAuthenticated(false);
      clearAuthToken();
    }
    setAuthError(null);
    setAuthChecked(true);
    return payload;
  };

  const logout = async (shouldRedirect = true) => {
    if (isDevAuthBypass()) {
      clearAdminGateTokens();
      clearAuthToken();
      setUser(null);
      setIsAuthenticated(false);
      if (shouldRedirect) {
        window.location.href = "/login";
      }
      return;
    }
    await apiLogout();
    clearAdminGateTokens();
    setUser(null);
    setIsAuthenticated(false);
    if (shouldRedirect) {
      window.location.href = "/login";
    }
  };

  const navigateToLogin = () => {
    window.location.href = "/login";
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated,
        isLoadingAuth,
        isLoadingPublicSettings: false,
        authError,
        authChecked,
        devAuthBypass: isDevAuthBypass(),
        login,
        register,
        logout,
        navigateToLogin,
        checkUserAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
