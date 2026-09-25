"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
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

type LoadState = { kind: "loading" } | { kind: "signed-in"; user: StaffUser };

/**
 * P5/P6 foundation (E5): loads `GET /api/v1/auth/staff/me` once for the
 * whole `(staff)` route group and shares the signed-in user and role.
 *
 * `src/middleware.ts` only checks that the session cookie is *present*;
 * this `/me` call is the authoritative check. A 401 (expired/revoked
 * session) first clears the stale cookie via logout -- otherwise middleware
 * would bounce the `/login` navigation straight back -- then redirects to
 * `/login`. Children render only once the session is confirmed, so
 * `useStaffSession()` never returns a half-loaded session.
 */
export function StaffSessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;

    api
      .GET("/api/v1/auth/staff/me")
      .then(({ data }) => {
        if (cancelled) return;
        if (data) {
          setState({ kind: "signed-in", user: data });
          return;
        }
        api
          .POST("/api/v1/auth/staff/logout")
          .catch(() => {})
          .finally(() => {
            if (!cancelled) router.replace("/login");
          });
      })
      .catch(() => {
        if (!cancelled) router.replace("/login");
      });

    return () => {
      cancelled = true;
    };
    // Mount-only: the session is checked once per page load. `router` is
    // stable and only used from callbacks.
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

  if (!session) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p role="status" className="text-neutral-600">
          Checking session…
        </p>
      </main>
    );
  }

  return <StaffSessionContext.Provider value={session}>{children}</StaffSessionContext.Provider>;
}

/** The signed-in staff session. Only valid inside `StaffSessionProvider`. */
export function useStaffSession(): StaffSession {
  const session = useContext(StaffSessionContext);
  if (!session) throw new Error("useStaffSession must be used inside <StaffSessionProvider>");
  return session;
}
