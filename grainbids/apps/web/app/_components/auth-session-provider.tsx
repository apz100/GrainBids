"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { API_BASE, AuthSession, buildApiRequestInit } from "@/lib/api";

type AuthSessionState = {
  session: AuthSession | null;
  status: "loading" | "authenticated" | "unauthenticated";
  error: string | null;
  refresh: () => Promise<void>;
};

const AuthSessionContext = createContext<AuthSessionState | null>(null);

export function AuthSessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [status, setStatus] = useState<AuthSessionState["status"]>("loading");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setStatus("loading");
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/settings/session`, buildApiRequestInit({ cache: "no-store" }));
      if (response.ok) {
        const nextSession: AuthSession = await response.json();
        setSession(nextSession);
        setStatus("authenticated");
        return;
      }
      setSession(null);
      setStatus("unauthenticated");
      if (response.status !== 401 && response.status !== 403) {
        setError(`Session bootstrap failed (${response.status})`);
      }
    } catch (err) {
      setSession(null);
      setStatus("unauthenticated");
      setError(err instanceof Error ? err.message : "Session bootstrap failed");
    }
  }

  useEffect(() => {
    refresh().catch((err) => {
      setSession(null);
      setStatus("unauthenticated");
      setError(err instanceof Error ? err.message : "Session bootstrap failed");
    });
  }, []);

  const value = useMemo(() => ({ session, status, error, refresh }), [session, status, error]);

  return <AuthSessionContext.Provider value={value}>{children}</AuthSessionContext.Provider>;
}

export function useAuthSession(): AuthSessionState {
  const context = useContext(AuthSessionContext);
  if (!context) {
    throw new Error("useAuthSession must be used within AuthSessionProvider");
  }
  return context;
}
