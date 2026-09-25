import type { ClientListQuery } from "./api";

export const DEFAULT_SORT = "-last_activity";
export const DEFAULT_PAGE_SIZE = 25;

// spec.md CQ-026 "Backend": exactly these three sort tokens, plus an id
// tie-break the backend adds on its own.
export const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: "-last_activity", label: "Most recent activity" },
  { value: "-created_at", label: "Newest client" },
  { value: "name", label: "Name (A–Z)" },
];

export const HAS_ACTIVE_OPTIONS: { value: ClientFilters["hasActive"]; label: string }[] = [
  { value: "", label: "Any" },
  { value: "true", label: "Active only" },
  { value: "false", label: "No active application" },
];

export interface ClientFilters {
  q: string;
  loId: string;
  createdFrom: string;
  createdTo: string;
  hasActive: "" | "true" | "false";
  sort: string;
  page: number;
  pageSize: number;
}

export const DEFAULT_FILTERS: ClientFilters = {
  q: "",
  loId: "",
  createdFrom: "",
  createdTo: "",
  hasActive: "",
  sort: DEFAULT_SORT,
  page: 1,
  pageSize: DEFAULT_PAGE_SIZE,
};

export function parseFiltersFromSearchParams(params: URLSearchParams): ClientFilters {
  const page = Number.parseInt(params.get("page") ?? "", 10);
  const pageSize = Number.parseInt(params.get("page_size") ?? "", 10);
  const hasActive = params.get("has_active");

  return {
    q: params.get("q") ?? "",
    loId: params.get("lo_id") ?? "",
    createdFrom: params.get("created_from") ?? "",
    createdTo: params.get("created_to") ?? "",
    hasActive: hasActive === "true" || hasActive === "false" ? hasActive : "",
    sort: params.get("sort") ?? DEFAULT_SORT,
    page: Number.isFinite(page) && page > 0 ? page : 1,
    pageSize: Number.isFinite(pageSize) && pageSize > 0 ? pageSize : DEFAULT_PAGE_SIZE,
  };
}

/** Only non-default values are written, so a freshly-cleared filter bar
 * produces a bare `/clients` URL (AC6). */
export function filtersToSearchParams(filters: ClientFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.loId) params.set("lo_id", filters.loId);
  if (filters.createdFrom) params.set("created_from", filters.createdFrom);
  if (filters.createdTo) params.set("created_to", filters.createdTo);
  if (filters.hasActive) params.set("has_active", filters.hasActive);
  if (filters.sort && filters.sort !== DEFAULT_SORT) params.set("sort", filters.sort);
  if (filters.page > 1) params.set("page", String(filters.page));
  if (filters.pageSize !== DEFAULT_PAGE_SIZE) params.set("page_size", String(filters.pageSize));
  return params;
}

export function filtersToApiQuery(filters: ClientFilters): ClientListQuery {
  return {
    q: filters.q || undefined,
    lo_id: filters.loId || undefined,
    created_from: filters.createdFrom || undefined,
    created_to: filters.createdTo || undefined,
    has_active: filters.hasActive === "" ? undefined : filters.hasActive === "true",
    sort: filters.sort,
    page: filters.page,
    page_size: filters.pageSize,
  };
}

export function hasActiveFilters(filters: ClientFilters): boolean {
  return (
    filters.q !== "" ||
    filters.loId !== "" ||
    filters.createdFrom !== "" ||
    filters.createdTo !== "" ||
    filters.hasActive !== ""
  );
}
