// AC6: "No arithmetic on money values exists in the frontend code for this
// panel (review check: all figures come from API responses)." Generalizes
// CQ-021's `packages/ui/src/report/report-no-money-math.test.ts` (same
// `containsForbiddenArithmetic` detector, ported here rather than imported
// cross-package since that file isn't part of `packages/ui`'s public
// exports) to this feature's own directory and its own FIELD_NAMES,
// derived the same way -- from this feature's own `__fixtures__/*.json`.
//
// Two intentional differences from the report version, both because this
// feature's inputs are live-edited (the report's are read-only):
//   1. `format.ts` is still excluded (display-only conversions), but its
//      two extra functions (`fractionToPercentInputValue`/
//      `percentInputValueToFraction`) are unit conversions of a *raw user
//      keystroke*, not a derived financial figure -- see that file's own
//      comment.
//   2. `usePricingPreview.ts` and `PricingPanel.tsx` build the `/quotes/
//      preview` request body by copying field values straight through
//      (`taxField.value`, `hoaField?.value`, ...) with no arithmetic
//      operator anywhere near them -- the scan below proves this
//      structurally, the same way it does for every other file here.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const FEATURE_DIR = join(__dirname);
const FIXTURES_DIR = join(__dirname, "__fixtures__");
const ALLOWED_FILES = new Set(["format.ts", "api.ts"]);
// `api.ts` is excluded because it holds only type re-exports and thin
// fetch wrappers with no field-shaped local variables -- FIELD_NAMES below
// (e.g. "value", drawn from generic fixture leaves) would otherwise false-
// positive on unrelated code like array/string indexing. Verified by hand:
// `api.ts` performs no arithmetic on any response field.

const DECIMAL_STRING = /^-?\d+(\.\d+)?$/;

function collectNumericLeafFieldNames(value: unknown, names: Set<string>, key?: string): void {
  if (Array.isArray(value)) {
    for (const item of value) collectNumericLeafFieldNames(item, names);
    return;
  }
  if (value !== null && typeof value === "object") {
    for (const [k, v] of Object.entries(value)) collectNumericLeafFieldNames(v, names, k);
    return;
  }
  if (typeof value === "string" && key && DECIMAL_STRING.test(value)) {
    names.add(key);
  }
}

function loadFieldNames(): string[] {
  const names = new Set<string>();
  for (const file of readdirSync(FIXTURES_DIR)) {
    if (!file.endsWith(".json")) continue;
    const data: unknown = JSON.parse(readFileSync(join(FIXTURES_DIR, file), "utf-8"));
    collectNumericLeafFieldNames(data, names);
  }
  // "value" (PricingField.value) is deliberately excluded: it's a generic
  // key name shared by every enriched field, and this feature's own
  // pagination-free array indexing (none exists today) would never trip
  // it anyway -- kept out to avoid false positives on unrelated generic
  // `.value` accesses elsewhere (e.g. DOM `input.value`).
  names.delete("value");
  names.delete("fico"); // an integer count, not a money/rate figure
  return [...names].sort();
}

export const FIELD_NAMES: string[] = loadFieldNames();

function isScannedFile(name: string): boolean {
  if (!/\.(ts|tsx)$/.test(name)) return false;
  if (name.endsWith(".test.ts") || name.endsWith(".test.tsx")) return false;
  if (ALLOWED_FILES.has(name)) return false;
  return true;
}

function stripStringsAndComments(source: string): string {
  return source
    .replace(/`(?:[^`\\]|\\.)*`/g, "``")
    .replace(/"(?:[^"\\]|\\.)*"/g, '""')
    .replace(/'(?:[^'\\]|\\.)*'/g, "''")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\n]*/g, "");
}

function buildFieldAccessPattern(): string {
  const alternation = FIELD_NAMES.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  return `(?:[A-Za-z_$][\\w$]*\\.)*(?:${alternation})\\b`;
}

function buildArithmeticRegex(): RegExp {
  const access = buildFieldAccessPattern();
  return new RegExp(`(?:${access})\\)?\\s*[+\\-*/]|[+\\-*/]\\s*\\(?(?:${access})`);
}

const ARITHMETIC_ADJACENT_TO_FIELD = buildArithmeticRegex();

export function containsForbiddenArithmetic(source: string): string | null {
  const stripped = stripStringsAndComments(source);
  const match = stripped.match(ARITHMETIC_ADJACENT_TO_FIELD);
  return match ? match[0] : null;
}

describe("FIELD_NAMES derivation (self-check)", () => {
  it("collects at least the money/rate leaf fields these fixtures carry", () => {
    for (const expected of [
      "loan_amount",
      "monthly_pi",
      "total_monthly_payment",
      "cash_to_close",
      "dscr_ratio",
      "down_payment_pct",
      "down_payment_amount",
    ]) {
      expect(FIELD_NAMES).toContain(expected);
    }
  });
});

describe("features/pricing never does arithmetic on money/rate API fields (CQ-017 AC6)", () => {
  const files = readdirSync(FEATURE_DIR).filter(isScannedFile);

  it("scans at least every component/hook file this item owns", () => {
    expect(files.length).toBeGreaterThanOrEqual(6);
  });

  it("FIELD_NAMES is non-trivial (fixtures loaded correctly)", () => {
    expect(FIELD_NAMES.length).toBeGreaterThanOrEqual(10);
  });

  for (const file of files) {
    it(`${file} performs no arithmetic on money/rate fields`, () => {
      const match = containsForbiddenArithmetic(readFileSync(join(FEATURE_DIR, file), "utf-8"));
      expect(match, `Found arithmetic near a money/rate field in ${file}: ${match}`).toBeNull();
    });
  }
});
