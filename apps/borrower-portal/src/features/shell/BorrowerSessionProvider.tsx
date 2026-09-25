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

type LoadState = { kind: "loading" } | { kind: "signed-in"; me: BorrowerMe } | { kind: "error" };

/**
 * P5/P6 foundation (E6): loads `GET /api/v1/auth/borrower/me` once for the
 * whole `(portal)` route group and shares it via `useBorrowerSession()`.
 *
 * `src/middleware.ts` only checks the cookie is *present*; this `/me` call
 * is the authoritative check. Only a 401 clears the stale cookie via logout
 * (else middleware bounces `/login` straight back) and redirects to
 * `/login?next=<current path>`, so signing in returns the borrower here.
 * Any other failure (network error, 5xx) is not a "you're signed out"
 * signal, so it neither logs out nor redirects: it shows a retry state
 * instead (review round 1). Children render only once the session is
 * confirmed.
 */
export function BorrowerSessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname() ?? "/";
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
    const search = typeof window === "undefined" ? "" : window.location.search;
    const loginUrl = loginUrlFor(pathname + search);
    try {
      const { data, response } = await api.GET("/api/v1/auth/borrower/me");
      if (!mountedRef.current) return;
      if (data) {
        setState({ kind: "signed-in", me: data });
        return;
      }
      if (response.status === 401) {
        try {
          await api.POST("/api/v1/auth/borrower/logout");
        } catch {
          // ignore -- still navigate away below
        }
        if (mountedRef.current) router.replace(loginUrl);
        return;
      }
      setState({ kind: "error" });
    } catch {
      if (mountedRef.current) setState({ kind: "error" });
    }
  }, [pathname, router]);

  useEffect(() => {
    void loadSession();
    // Mount-only: the session is checked once when the portal loads (the
    // `(portal)` layout persists across its pages). `loadSession` is
    // re-created if `pathname` changes, but that must not re-trigger the
    // initial check.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refresh = useCallback(async () => {
    const { data } = await api.GET("/api/v1/auth/borrower/me");
    if (data) setState({ kind: "signed-in", me: data });
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

  const session = useMemo<BorrowerSession | null>(() => {
    if (state.kind !== "signed-in") return null;
    return { me: state.me, refresh, logout };
  }, [state, refresh, logout]);

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
