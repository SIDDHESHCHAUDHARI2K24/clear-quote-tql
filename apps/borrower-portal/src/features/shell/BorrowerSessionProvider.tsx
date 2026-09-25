"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";

import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";
import { loginUrlFor } from "./nav";

export type BorrowerMe = components["schemas"]["BorrowerMeOut"];

export interface BorrowerSession {
  me: BorrowerMe;
  /** Re-fetches `/me` (e.g. after CQ-032's submit creates an application). */
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const BorrowerSessionContext = createContext<BorrowerSession | null>(null);

/**
 * P5/P6 foundation (E6): loads `GET /api/v1/auth/borrower/me` once for the
 * whole `(portal)` route group and shares it via `useBorrowerSession()`.
 *
 * `src/middleware.ts` only checks the cookie is *present*; this `/me` call
 * is the authoritative check. On a 401 it clears the stale cookie via
 * logout (else middleware bounces `/login` straight back) and redirects to
 * `/login?next=<current path>`, so signing in returns the borrower here.
 * Children render only once the session is confirmed.
 */
export function BorrowerSessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname() ?? "/";
  const [me, setMe] = useState<BorrowerMe | null>(null);

  useEffect(() => {
    let cancelled = false;
    const search = typeof window === "undefined" ? "" : window.location.search;
    const loginUrl = loginUrlFor(pathname + search);

    api
      .GET("/api/v1/auth/borrower/me")
      .then(({ data }) => {
        if (cancelled) return;
        if (data) {
          setMe(data);
          return;
        }
        api
          .POST("/api/v1/auth/borrower/logout")
          .catch(() => {})
          .finally(() => {
            if (!cancelled) router.replace(loginUrl);
          });
      })
      .catch(() => {
        if (!cancelled) router.replace(loginUrl);
      });

    return () => {
      cancelled = true;
    };
    // Mount-only: the session is checked once when the portal loads (the
    // `(portal)` layout persists across its pages). `router`/`pathname`
    // are read only for the initial redirect target.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refresh = useCallback(async () => {
    const { data } = await api.GET("/api/v1/auth/borrower/me");
    if (data) setMe(data);
  }, []);

  const logout = useCallback(async () => {
    // Best-effort: even if the request fails the borrower's intent is to
    // leave; any un-cleared cookie is caught by the next /me check.
    try {
      await api.POST("/api/v1/auth/borrower/logout");
    } catch {
      // ignore -- still navigate away below
    }
    router.replace("/login");
  }, [router]);

  const session = useMemo<BorrowerSession | null>(
    () => (me ? { me, refresh, logout } : null),
    [me, refresh, logout],
  );

  if (!session) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p role="status" className="text-neutral-600">
          Checking session…
        </p>
      </main>
    );
  }

  return (
    <BorrowerSessionContext.Provider value={session}>{children}</BorrowerSessionContext.Provider>
  );
}

/** The signed-in borrower session. Only valid inside `BorrowerSessionProvider`. */
export function useBorrowerSession(): BorrowerSession {
  const session = useContext(BorrowerSessionContext);
  if (!session) {
    throw new Error("useBorrowerSession must be used inside <BorrowerSessionProvider>");
  }
  return session;
}
