"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import {
  filtersToSearchParams,
  parseFiltersFromSearchParams,
  type ApplicationFilters,
} from "./filters";

export interface UseApplicationFiltersResult {
  filters: ApplicationFilters;
  /** Merges `patch` into the current filters and pushes the new URL. Any
   * change other than `page` itself resets `page` back to 1 (spec.md:
   * changing a filter should show its first page of results). */
  setFilters: (patch: Partial<ApplicationFilters>) => void;
  clearFilters: () => void;
}

/** spec.md "All filters in the URL": reads/writes every filter (and sort,
 * page, page_size) as `useSearchParams()` query params via
 * `router.push` -- so a reload or back-navigation restores the exact same
 * table (AC6), and CQ-025's dashboard tile links land here pre-filtered. */
export function useApplicationFilters(): UseApplicationFiltersResult {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const filters = useMemo(() => parseFiltersFromSearchParams(searchParams), [searchParams]);

  const setFilters = useCallback(
    (patch: Partial<ApplicationFilters>) => {
      const resetsPage = Object.keys(patch).some((key) => key !== "page");
      const next: ApplicationFilters = {
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
