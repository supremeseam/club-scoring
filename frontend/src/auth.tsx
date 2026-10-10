import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, type S } from "./api/client";

type Ctx = {
  user: S["Me"] | null;
  loading: boolean;
  expired: boolean;                 // the session ended while the person was using the site
  refresh: () => Promise<void>;
  clearExpired: () => void;
};
const AuthCtx = createContext<Ctx>({ user: null, loading: true, expired: false, refresh: async () => {}, clearExpired: () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [expired, setExpired] = useState(false);
  const q = useQuery({
    queryKey: ["me"],
    queryFn: () => api<S["Me"]>("/auth/me").catch(() => null),
    staleTime: 60_000,
  });
  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ["me"] });
  };
  useEffect(() => {
    // api() raises these when the server says the session is over / a temporary password must be replaced
    const onExpired = () => {
      setExpired(true);
      qc.setQueryData(["me"], null);
    };
    const onMustChange = () => void qc.invalidateQueries({ queryKey: ["me"] });
    window.addEventListener("session-expired", onExpired);
    window.addEventListener("password-change-required", onMustChange);
    return () => {
      window.removeEventListener("session-expired", onExpired);
      window.removeEventListener("password-change-required", onMustChange);
    };
  }, [qc]);
  return (
    <AuthCtx.Provider value={{ user: q.data ?? null, loading: q.isLoading, expired, refresh, clearExpired: () => setExpired(false) }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);

/** Signed-in race committee only. Someone holding a temporary password goes to choose their own first. */
export function RequireEditor({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return null;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  if (user.must_change_password) return <Navigate to="/change-password" replace />;
  return <>{children}</>;
}

/** Signed in, whether or not a password change is pending (used by the change-password page). */
export function RequireSignedIn({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return null;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  return <>{children}</>;
}
