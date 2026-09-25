// AC7: "ReportViewModel round-trips: the Pydantic model's JSON validates
// against the generated TypeScript type in a type test." `tsc --noEmit`
// (part of `pnpm -r run typecheck` / `make lint`) fails the build if a
// fixture's shape (built by backend/scripts/build_report_fixtures.py from
// the Pydantic `ReportViewModel`) ever drifts from the api-client's
// generated type (built from the same Pydantic model via
// `report_view_model_openapi_components`, see schemas.py) -- a missing
// field, a renamed field, or a field whose JSON type no longer overlaps
// `ReportViewModelData`'s (e.g. a number where a decimal *string* is
// required) fails the `const typed: ReportViewModelData = fixture` line
// below for every fixture (PR review finding N1: a real structural
// assignment, not a hand-rolled shallow runtime check standing in for one).
//
// The one carve-out: TypeScript's `resolveJsonModule` infers a JSON import's
// string-literal properties as the widened `string` type, not the literal
// union `ReportStrategy` ("primary" | "ltr" | "str") expects -- confirmed by
// trying the direct assignment first, which fails to compile with exactly
// `Type 'string' is not assignable to type '"primary" | "ltr" | "str"'` and
// nothing else (every other field lines up). `LooseReportViewModel` loosens
// only that one field to `string`; `assertValidStrategy` below is a real
// runtime check (not a cast) that narrows it back before the final
// `ReportViewModelData`-typed assignment, so a genuinely wrong/typo'd
// strategy value still fails (at runtime here, at compile time for every
// other field).
import { describe, expect, it } from "vitest";

import type { ReportViewModelData } from "../types";
import danielOrtiz from "./daniel_ortiz.json";
import kathleenMcreynolds from "./kathleen_mcreynolds.json";
import marcusHale from "./marcus_hale.json";
import marcusHaleExpired from "./marcus_hale_expired.json";
import priyaNair from "./priya_nair.json";
import priyaNairSuperseded from "./priya_nair_superseded.json";

type LooseReportViewModel = Omit<ReportViewModelData, "strategy"> & { strategy: string };

function assertValidStrategy(
  data: LooseReportViewModel,
  label: string,
): asserts data is LooseReportViewModel & { strategy: ReportViewModelData["strategy"] } {
  if (data.strategy !== "primary" && data.strategy !== "ltr" && data.strategy !== "str") {
    throw new Error(`${label}.strategy is not a valid ReportStrategy: ${String(data.strategy)}`);
  }
}

function loadFixture(data: LooseReportViewModel, label: string): ReportViewModelData {
  assertValidStrategy(data, label);
  // Every field other than `strategy` was already structurally verified by
  // the `LooseReportViewModel` parameter type above (identical to
  // `ReportViewModelData` field-for-field, per the Omit/intersection).
  return data;
}

// Real structural assignment: the LooseReportViewModel type annotation on
// each JSON import (below, at the loadFixture call) is what actually
// exercises `tsc --noEmit` against every field's name, nesting and type --
// not just a spot-checked subset.
const _marcusHale = loadFixture(marcusHale, "marcus_hale");
const _marcusHaleExpired = loadFixture(marcusHaleExpired, "marcus_hale_expired");
const _kathleenMcreynolds = loadFixture(kathleenMcreynolds, "kathleen_mcreynolds");
const _priyaNair = loadFixture(priyaNair, "priya_nair");
const _priyaNairSuperseded = loadFixture(priyaNairSuperseded, "priya_nair_superseded");
const _danielOrtiz = loadFixture(danielOrtiz, "daniel_ortiz");

describe("ReportViewModel fixtures type-check against the generated api-client type", () => {
  it("every fixture is a valid ReportViewModelData (compile-time structural + runtime strategy check)", () => {
    for (const fixture of [
      _marcusHale,
      _marcusHaleExpired,
      _kathleenMcreynolds,
      _priyaNair,
      _priyaNairSuperseded,
      _danielOrtiz,
    ]) {
      expect(fixture.header).toBeTruthy();
      expect(["primary", "ltr", "str"]).toContain(fixture.strategy);
      expect(Array.isArray(fixture.options)).toBe(true);
      expect(fixture.options.length).toBeGreaterThan(0);
    }
  });

  it("rejects a fixture with an invalid strategy value at runtime", () => {
    const bad = { ..._priyaNair, strategy: "not-a-real-strategy" } as LooseReportViewModel;
    expect(() => loadFixture(bad, "bad-fixture")).toThrow(/not a valid ReportStrategy/);
  });
});
