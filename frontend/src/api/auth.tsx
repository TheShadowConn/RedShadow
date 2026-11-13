import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "./client";
import type { Me } from "./types";

export const ME_KEY = ["me"] as const;

async function loadMe(): Promise<Me | null> {
  try {
    return await api<Me>("GET", "/auth/me");
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    throw e;
  }
}

type AuthState = { me: Me | null; loading: boolean; error: Error | null; refresh: () => Promise<unknown>; can: (code: string) => boolean };

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ME_KEY, queryFn: loadMe, retry: false, refetchOnWindowFocus: true });

  useEffect(() => {
    const onExpired = () => qc.setQueryData(ME_KEY, null);
    window.addEventListener("rs:unauthenticated", onExpired);
    return () => window.removeEventListener("rs:unauthenticated", onExpired);
  }, [qc]);

  const me = q.data ?? null;
  const value: AuthState = {
    me,
    loading: q.isPending,
    error: q.error,
    refresh: () => qc.invalidateQueries({ queryKey: ME_KEY }),
    can: (code) => !!me && me.restriction === null && me.permissions.includes(code),
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
