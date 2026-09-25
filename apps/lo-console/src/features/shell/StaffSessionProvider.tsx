"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";

import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type StaffUser = components["schemas"]["StaffUserOut"];
export type StaffRole = StaffUser["role"];

export interface StaffSession {
  user: StaffUser;
  role: StaffRole;
  isAdmin: boolean;
  isManagerOrAdmin: boolean;
  logout: () => Promise<void>;
}

const StaffSessionContext = createContext<StaffSession | null>(null);

type LoadState = { kind: "loading" } | { kind: "signed-in"; user: StaffUser } | { kind: "error" };

/**
 * P5/P6 foundation (E5): loads `GET /api/v1/auth/staff/me` once for the
 * whole `(staff)` route group and shares the signed-in user and role.
 *
 * `src/middleware.ts` only checks that the session cookie is *present*;
 * this `/me` call is the authoritative check. Only a 401 (expired/revoked
 * session) clears the stale cookie via logout -- otherwise middleware
 * would bounce the `/login` navigation straight back -- then redirects to
 * `/login`. Any other failure (network error, 5xx) is not a "you're signed
 * out" signal, so it neither logs out nor redirects: it shows a retry
 * state instead (review round 1). Children render only once the session is
 * confirmed, so `useStaffSession()` never returns a half-loaded session.
 */
export function StaffSessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const loadSession = useCallback(async () => {
    if (mountedRef.current) setState({ kind: "loading" });
    try {
      const { data, response } = await api.GET("/api/v1/auth/staff/me");
      if (!mountedRef.current) return;
      if (data) {
        setState({ kind: "signed-in", user: data });
        return;
      }
      if (response.status === 401) {
        try {
          await api.POST("/api/v1/auth/staff/logout");
        } catch {
          // ignore -- still navigate away below
        }
        if (mountedRef.current) router.replace("/login");
        return;
      }
      setState({ kind: "error" });
    } catch {
      if (mountedRef.current) setState({ kind: "error" });
    }
  }, [router]);

  useEffect(() => {
    void loadSession();
    // Mount-only: the session is checked once per page load. `loadSession`
    // is re-created only if `router` changes, which does not happen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const logout = useCallback(async () => {
    // Best-effort: even if the request fails the user's intent is to leave;
    // any un-cleared cookie is caught by the next /me check.
    try {
      await api.POST("/api/v1/auth/staff/logout");
    } catch {
      // ignore -- still navigate away below
    }
    router.replace("/login");
  }, [router]);

  const session = useMemo<StaffSession | null>(() => {
    if (state.kind !== "signed-in") return null;
    const { user } = state;
    return {
      user,
      role: user.role,
      isAdmin: user.role === "admin",
      isManagerOrAdmin: user.role === "admin" || user.role === "manager",
      logout,
    };
  }, [state, logout]);

  if (state.kind === "loading") {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p role="status" className="text-neutral-600">
          Checking session…
        </p>
      </main>
    );
  }

  if (state.kind === "error") {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <div role="alert" className="flex flex-col items-center gap-3 text-center">
          <p className="text-neutral-600">Can&apos;t reach the server</p>
          <button
            type="button"
            onClick={() => void loadSession()}
            className="rounded-md border border-navy-500 px-4 py-2 text-sm font-medium text-navy-900 hover:bg-navy-50"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  if (!session) return null;

  return <StaffSessionContext.Provider value={session}>{children}</StaffSessionContext.Provider>;
}

/** The signed-in staff session. Only valid inside `StaffSessionProvider`. */
export function useStaffSession(): StaffSession {
  const session = useContext(StaffSessionContext);
  if (!session) throw new Error("useStaffSession must be used inside <StaffSessionProvider>");
  return session;
}
