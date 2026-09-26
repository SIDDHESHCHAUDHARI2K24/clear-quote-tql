import { describe, expect, it } from "vitest";

import {
  DEFAULT_FILTERS,
  filtersToApiQuery,
  filtersToSearchParams,
  hasActiveFilters,
  parseFiltersFromSearchParams,
} from "./filters";

describe("parseFiltersFromSearchParams", () => {
  it("returns defaults for an empty URL", () => {
    expect(parseFiltersFromSearchParams(new URLSearchParams(""))).toEqual(DEFAULT_FILTERS);
  });

  it("parses every filter", () => {
    const params = new URLSearchParams(
      "q=hale&lo_id=abc&created_from=2026-01-01&created_to=2026-01-31&has_active=true&sort=name&page=3&page_size=50",
    );
    expect(parseFiltersFromSearchParams(params)).toEqual({
      q: "hale",
      loId: "abc",
      createdFrom: "2026-01-01",
      createdTo: "2026-01-31",
      hasActive: "true",
      sort: "name",
      page: 3,
      pageSize: 50,
    });
  });

  it("falls back to page 1 / default page_size for invalid values", () => {
    const params = new URLSearchParams("page=0&page_size=abc");
    const filters = parseFiltersFromSearchParams(params);
    expect(filters.page).toBe(1);
    expect(filters.pageSize).toBe(25);
  });

  it("ignores an invalid has_active value", () => {
    expect(parseFiltersFromSearchParams(new URLSearchParams("has_active=maybe")).hasActive).toBe(
      "",
    );
  });
});

describe("filtersToSearchParams", () => {
  it("produces an empty string for default filters", () => {
    expect(filtersToSearchParams(DEFAULT_FILTERS).toString()).toBe("");
  });

  it("round-trips through parseFiltersFromSearchParams", () => {
    const filters = {
      ...DEFAULT_FILTERS,
      q: "hale",
      loId: "abc",
      createdFrom: "2026-01-01",
      createdTo: "2026-01-31",
      hasActive: "true" as const,
      sort: "name",
      page: 2,
      pageSize: 50,
    };
    const roundTripped = parseFiltersFromSearchParams(filtersToSearchParams(filters));
    expect(roundTripped).toEqual(filters);
  });
});

describe("filtersToApiQuery", () => {
  it("omits empty fields and converts has_active to a boolean", () => {
    const query = filtersToApiQuery({ ...DEFAULT_FILTERS, hasActive: "false" });
    expect(query.has_active).toBe(false);
    expect(query.q).toBeUndefined();
    expect(query.lo_id).toBeUndefined();

    const query2 = filtersToApiQuery(DEFAULT_FILTERS);
    expect(query2.has_active).toBeUndefined();
  });
});

describe("hasActiveFilters", () => {
  it("is false for defaults, true once any filter is set", () => {
    expect(hasActiveFilters(DEFAULT_FILTERS)).toBe(false);
    expect(hasActiveFilters({ ...DEFAULT_FILTERS, q: "x" })).toBe(true);
    expect(hasActiveFilters({ ...DEFAULT_FILTERS, hasActive: "true" })).toBe(true);
  });
});
