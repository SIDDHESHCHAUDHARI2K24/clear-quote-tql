import type { ApplicationListQuery } from "./api";

// spec.md "Backend" status parameter: a comma list of the spec's own
// status labels (which CQ-025's tile links use verbatim, e.g.
// `?status=NeedsAttention`), plus the raw snake_case enum value, plus the
// `sent_or_later` alias. This filter bar's `MultiSelect` uses the
// snake_case value as its canonical, stable option id (matching
// `@cq/ui`'s `ApplicationStatus` union) and writes that same form back to
// the URL -- the backend accepts both forms on read (plan.md Decision #7),
// so there's no need to round-trip through PascalCase.
export const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "sent_or_later", label: "Sent or later" },
  { value: "intake", label: "Intake" },
  { value: "verifying", label: "Verifying" },
  { value: "needs_attention", label: "Needs attention" },
  { value: "ready_to_price", label: "Ready to price" },
  { value: "priced", label: "Priced" },
  { value: "sent", label: "Sent" },
  { value: "viewed", label: "Viewed" },
  { value: "option_selected", label: "Option selected" },
  { value: "inquiry", label: "Inquiry" },
  { value: "stale", label: "Stale" },
  { value: "withdrawn", label: "Withdrawn" },
  { value: "closed", label: "Closed" },
];

export const STRATEGY_OPTIONS: { value: string; label: string }[] = [
  { value: "primary", label: "Primary" },
  { value: "ltr", label: "LTR" },
  { value: "str", label: "STR" },
];

export const DEFAULT_SORT = "-updated_at";
export const DEFAULT_PAGE_SIZE = 25;

export const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: "-updated_at", label: "Recently updated" },
  { value: "amount", label: "Purchase price (low to high)" },
  { value: "-amount", label: "Purchase price (high to low)" },
  { value: "client", label: "Client name" },
  { value: "status", label: "Status" },
];

export interface ApplicationFilters {
  q: string;
  status: string[];
  strategy: string[];
  amountMin: string;
  amountMax: string;
  state: string;
  hasProperty: "" | "true" | "false";
  createdFrom: string;
  createdTo: string;
  loId: string;
  sort: string;
  page: number;
  pageSize: number;
}

export const DEFAULT_FILTERS: ApplicationFilters = {
  q: "",
  status: [],
  strategy: [],
  amountMin: "",
  amountMax: "",
  state: "",
  hasProperty: "",
  createdFrom: "",
  createdTo: "",
  loId: "",
  sort: DEFAULT_SORT,
  page: 1,
  pageSize: DEFAULT_PAGE_SIZE,
};

/** `NeedsAttention` -> `needs_attention` (the inverse of the backend's
 * `_pascal_label`) -- a raw snake_case token or the `sent_or_later` alias
 * passes through unchanged. */
function normalizeStatusToken(token: string): string {
  if (token === "sent_or_later" || token.includes("_")) return token;
  if (token !== token.toLowerCase() && token[0] === token[0]?.toUpperCase()) {
    return token.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
  }
  return token.toLowerCase();
}

export function parseFiltersFromSearchParams(params: URLSearchParams): ApplicationFilters {
  const status = params.get("status");
  const strategy = params.get("strategy");
  const page = Number.parseInt(params.get("page") ?? "", 10);
  const pageSize = Number.parseInt(params.get("page_size") ?? "", 10);
  const hasProperty = params.get("has_property");

  return {
    q: params.get("q") ?? "",
    status: status
      ? status
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean)
          .map(normalizeStatusToken)
      : [],
    strategy: strategy
      ? strategy
          .split(",")
          .map((t) => t.trim().toLowerCase())
          .filter(Boolean)
      : [],
    amountMin: params.get("amount_min") ?? "",
    amountMax: params.get("amount_max") ?? "",
    state: params.get("state") ?? "",
    hasProperty: hasProperty === "true" || hasProperty === "false" ? hasProperty : "",
    createdFrom: params.get("created_from") ?? "",
    createdTo: params.get("created_to") ?? "",
    loId: params.get("lo_id") ?? "",
    sort: params.get("sort") ?? DEFAULT_SORT,
    page: Number.isFinite(page) && page > 0 ? page : 1,
    pageSize: Number.isFinite(pageSize) && pageSize > 0 ? pageSize : DEFAULT_PAGE_SIZE,
  };
}

/** Only non-default values are written, so a freshly-cleared filter bar
 * produces a bare `/applications` URL. */
export function filtersToSearchParams(filters: ApplicationFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.status.length > 0) params.set("status", filters.status.join(","));
  if (filters.strategy.length > 0) params.set("strategy", filters.strategy.join(","));
  if (filters.amountMin) params.set("amount_min", filters.amountMin);
  if (filters.amountMax) params.set("amount_max", filters.amountMax);
  if (filters.state) params.set("state", filters.state);
  if (filters.hasProperty) params.set("has_property", filters.hasProperty);
  if (filters.createdFrom) params.set("created_from", filters.createdFrom);
  if (filters.createdTo) params.set("created_to", filters.createdTo);
  if (filters.loId) params.set("lo_id", filters.loId);
  if (filters.sort && filters.sort !== DEFAULT_SORT) params.set("sort", filters.sort);
  if (filters.page > 1) params.set("page", String(filters.page));
  if (filters.pageSize !== DEFAULT_PAGE_SIZE) params.set("page_size", String(filters.pageSize));
  return params;
}

export function filtersToApiQuery(filters: ApplicationFilters): ApplicationListQuery {
  return {
    q: filters.q || undefined,
    status: filters.status.length > 0 ? filters.status.join(",") : undefined,
    strategy: filters.strategy.length > 0 ? filters.strategy.join(",") : undefined,
    amount_min: filters.amountMin || undefined,
    amount_max: filters.amountMax || undefined,
    state: filters.state || undefined,
    has_property: filters.hasProperty === "" ? undefined : filters.hasProperty === "true",
    created_from: filters.createdFrom || undefined,
    created_to: filters.createdTo || undefined,
    lo_id: filters.loId || undefined,
    sort: filters.sort,
    page: filters.page,
    page_size: filters.pageSize,
  };
}

export function hasActiveFilters(filters: ApplicationFilters): boolean {
  return (
    filters.q !== "" ||
    filters.status.length > 0 ||
    filters.strategy.length > 0 ||
    filters.amountMin !== "" ||
    filters.amountMax !== "" ||
    filters.state !== "" ||
    filters.hasProperty !== "" ||
    filters.createdFrom !== "" ||
    filters.createdTo !== "" ||
    filters.loId !== ""
  );
}
