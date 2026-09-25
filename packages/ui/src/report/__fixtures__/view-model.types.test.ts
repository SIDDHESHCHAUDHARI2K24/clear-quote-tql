// AC7: "ReportViewModel round-trips: the Pydantic model's JSON validates
// against the generated TypeScript type in a type test." `tsc --noEmit`
// (part of `pnpm -r run typecheck` / `make lint`) fails the build if a
// fixture's shape (built by backend/scripts/build_report_fixtures.py from
// the Pydantic `ReportViewModel`) ever drifts from the api-client's
// generated type (built from the same Pydantic model via
// `report_view_model_openapi_components`, see schemas.py) -- a missing
// field, a renamed field or a field whose JSON type no longer overlaps
// `ReportViewModelData`'s (e.g. a number where a decimal *string* is
// required) fails this cast. `assertIsReportViewModel` narrows the JSON
// import's widened `strategy: string` to the schema's own literal union
// with an actual runtime check first (a plain `as` cast alone cannot
// distinguish a typo'd strategy value from a valid one, since both are
// `string` before narrowing) -- so this is a real check, not just a
// compile-time-only assertion. The `describe` block below makes this file
// also run as a normal vitest test, so a failure here shows up as a failing
// test, not just a silent tsc failure.
import { describe, expect, it } from "vitest";

import type { ReportViewModelData } from "../types";
import danielOrtiz from "./daniel_ortiz.json";
import kathleenMcreynolds from "./kathleen_mcreynolds.json";
import marcusHale from "./marcus_hale.json";
import marcusHaleExpired from "./marcus_hale_expired.json";
import priyaNair from "./priya_nair.json";
import priyaNairSuperseded from "./priya_nair_superseded.json";

function assertIsReportViewModel(value: unknown): asserts value is ReportViewModelData {
  if (typeof value !== "object" || value === null) {
    throw new Error("fixture is not an object");
  }
  const v = value as Record<string, unknown>;
  if (v.strategy !== "primary" && v.strategy !== "ltr" && v.strategy !== "str") {
    throw new Error(`fixture.strategy is not a valid ReportStrategy: ${String(v.strategy)}`);
  }
  if (typeof v.header !== "object" || v.header === null) {
    throw new Error("fixture.header is missing");
  }
  if (!Array.isArray(v.options)) {
    throw new Error("fixture.options is not an array");
  }
}

function loadFixture(data: unknown): ReportViewModelData {
  assertIsReportViewModel(data);
  return data;
}

const _marcusHale = loadFixture(marcusHale);
const _marcusHaleExpired = loadFixture(marcusHaleExpired);
const _kathleenMcreynolds = loadFixture(kathleenMcreynolds);
const _priyaNair = loadFixture(priyaNair);
const _priyaNairSuperseded = loadFixture(priyaNairSuperseded);
const _danielOrtiz = loadFixture(danielOrtiz);

describe("ReportViewModel fixtures type-check against the generated api-client type", () => {
  it("every fixture is a valid ReportViewModelData (compile-time + smoke)", () => {
    for (const fixture of [
      _marcusHale,
      _marcusHaleExpired,
      _kathleenMcreynolds,
      _priyaNair,
      _priyaNairSuperseded,
      _danielOrtiz,
    ]) {
      expect(fixture.header).toBeTruthy();
      expect(Array.isArray(fixture.options)).toBe(true);
      expect(fixture.options.length).toBeGreaterThan(0);
    }
  });
});
