"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import { filtersToSearchParams, parseFiltersFromSearchParams, type ClientFilters } from "./filters";

export interface UseClientFiltersResult {
  filters: ClientFilters;
  /** Merges `patch` into the current filters and pushes the new URL. Any
   * change other than `page` itself resets `page` back to 1. */
  setFilters: (patch: Partial<ClientFilters>) => void;
  clearFilters: () => void;
}

/** spec.md CQ-026 "Frontend": every filter (and sort, page, page_size)
 * lives in `useSearchParams()` via `router.push`, so a reload or
 * back-navigation restores the exact same table (AC6) -- same pattern as
 * `applications/useApplicationFilters.ts`. */
export function useClientFilters(): UseClientFiltersResult {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const filters = useMemo(() => parseFiltersFromSearchParams(searchParams), [searchParams]);

  const setFilters = useCallback(
    (patch: Partial<ClientFilters>) => {
      const resetsPage = Object.keys(patch).some((key) => key !== "page");
      const next: ClientFilters = {
        ...filters,
        ...patch,
        page: resetsPage ? 1 : (patch.page ?? filters.page),
      };
      const query = filtersToSearchParams(next).toString();
      router.push(query ? `${pathname}?${query}` : pathname);
    },
    [filters, pathname, router],
  );

  const clearFilters = useCallback(() => {
    router.push(pathname);
  }, [pathname, router]);

  return { filters, setFilters, clearFilters };
}
