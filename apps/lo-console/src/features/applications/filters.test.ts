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

  it("accepts CQ-025's dashboard tile link forms (E10)", () => {
    // ?status=sent_or_later
    expect(
      parseFiltersFromSearchParams(new URLSearchParams("status=sent_or_later")).status,
    ).toEqual(["sent_or_later"]);
    // ?has_property=true
    expect(parseFiltersFromSearchParams(new URLSearchParams("has_property=true")).hasProperty).toBe(
      "true",
    );
    // ?status=Priced,Inquiry,OptionSelected
    expect(
      parseFiltersFromSearchParams(new URLSearchParams("status=Priced,Inquiry,OptionSelected"))
        .status,
    ).toEqual(["priced", "inquiry", "option_selected"]);
    // ?status=NeedsAttention
    expect(
      parseFiltersFromSearchParams(new URLSearchParams("status=NeedsAttention")).status,
    ).toEqual(["needs_attention"]);
    // ?status=Stale
    expect(parseFiltersFromSearchParams(new URLSearchParams("status=Stale")).status).toEqual([
      "stale",
    ]);
  });

  it("also accepts the raw snake_case enum value", () => {
    expect(
      parseFiltersFromSearchParams(new URLSearchParams("status=needs_attention")).status,
    ).toEqual(["needs_attention"]);
  });

  it("parses every other filter", () => {
    const params = new URLSearchParams(
      "q=aisha&lo_id=abc&strategy=ltr,str&amount_min=100000&amount_max=200000&state=FL&created_from=2026-01-01&created_to=2026-01-31&sort=amount&page=3&page_size=50",
    );
    expect(parseFiltersFromSearchParams(params)).toEqual({
      q: "aisha",
      status: [],
      strategy: ["ltr", "str"],
      amountMin: "100000",
      amountMax: "200000",
      state: "FL",
      hasProperty: "",
      createdFrom: "2026-01-01",
      createdTo: "2026-01-31",
      loId: "abc",
      sort: "amount",
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
});

describe("filtersToSearchParams", () => {
  it("produces an empty string for default filters", () => {
    expect(filtersToSearchParams(DEFAULT_FILTERS).toString()).toBe("");
  });

  it("round-trips through parseFiltersFromSearchParams", () => {
    const filters = {
      ...DEFAULT_FILTERS,
      q: "grace",
      status: ["sent", "viewed"],
      strategy: ["ltr"],
      amountMin: "100000",
      state: "CO",
      hasProperty: "true" as const,
      page: 2,
      pageSize: 50,
      sort: "amount",
    };
    const roundTripped = parseFiltersFromSearchParams(filtersToSearchParams(filters));
    expect(roundTripped).toEqual(filters);
  });
});

describe("filtersToApiQuery", () => {
  it("omits empty fields and joins comma lists", () => {
    const query = filtersToApiQuery({
      ...DEFAULT_FILTERS,
      status: ["priced", "inquiry"],
      strategy: ["ltr"],
      hasProperty: "false",
    });
    expect(query.status).toBe("priced,inquiry");
    expect(query.strategy).toBe("ltr");
    expect(query.has_property).toBe(false);
    expect(query.q).toBeUndefined();
    expect(query.lo_id).toBeUndefined();
  });
});

describe("hasActiveFilters", () => {
  it("is false for defaults, true once any filter is set", () => {
    expect(hasActiveFilters(DEFAULT_FILTERS)).toBe(false);
    expect(hasActiveFilters({ ...DEFAULT_FILTERS, q: "x" })).toBe(true);
    expect(hasActiveFilters({ ...DEFAULT_FILTERS, status: ["priced"] })).toBe(true);
  });
});
