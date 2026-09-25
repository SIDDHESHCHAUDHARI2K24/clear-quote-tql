// AC5: "A static check fails the build if any file in
// packages/ui/src/report/ performs arithmetic on money props (lint rule or
// test that scans for `+ - * /` applied to those fields; document the
// approach in plan.md)." See CQ-021 plan.md Decision 4 for why this is a
// scan test rather than a custom eslint rule (no project-local eslint-rule
// package/build step existed to hang a new rule off).
//
// Approach (hardened per PR review finding M2): the set of "money/rate/
// percent leaf field names" is derived dynamically from the committed
// fixtures (packages/ui/src/report/__fixtures__/*.json) -- every ReportViewModel
// leaf value that is shaped like a decimal string (`^-?\d+(\.\d+)?$`) has
// its key name collected into FIELD_NAMES. This is self-updating: it never
// goes stale as ReportViewModel gains/renames fields, because it reads the
// same fixtures the type test (view-model.types.test.ts) and component
// tests already depend on.
//
// For every *.tsx/*.ts source file this item owns (excluding tests,
// fixtures, and this file's own two sanctioned formatters, format.ts and
// types.ts), strip string/template literals and comments (so Tailwind
// classes like "px-4" and JSDoc prose never false-positive), then scan what
// remains for an arithmetic operator (`+ - * /`) directly adjacent to a
// FIELD_NAMES access -- whether dotted (`option.hero.monthly_payment`),
// destructured (`const { monthly_payment } = option.hero; monthly_payment -
// x`), or a loop variable (`for (const line of lines) line.amount + y`).
// `containsForbiddenArithmetic` below is the single detector both the real
// scan and this file's own negative self-tests exercise, so the self-tests
// prove the actual detection logic, not a separate reimplementation of it.
//
// Known limitation (heuristic, not a full parser): a template literal's
// entire span -- including any `${...}` interpolated expression -- is
// stripped before scanning, so arithmetic written *inside* a template
// interpolation (e.g. `` `${a.rate - b.rate}` ``) would not be caught. No
// code in this directory does that today; a real parser would be needed to
// close this gap precisely, which is disproportionate for a defense-in-depth
// scan test layered on top of code review and the builder's own contract
// (money math lives in quote_engine/builder.py, never in these components).
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const REPORT_DIR = join(__dirname);
const FIXTURES_DIR = join(__dirname, "__fixtures__");
const ALLOWED_FILES = new Set(["format.ts", "types.ts"]);

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
    .replace(/`(?:[^`\\]|\\.)*`/g, "``") // template literals (incl. their ${} expressions)
    .replace(/"(?:[^"\\]|\\.)*"/g, '""') // double-quoted strings
    .replace(/'(?:[^'\\]|\\.)*'/g, "''") // single-quoted strings
    .replace(/\/\*[\s\S]*?\*\//g, "") // block comments
    .replace(/\/\/[^\n]*/g, ""); // line comments
}

/**
 * A ReportViewModel money/rate/percent leaf field access: an optional
 * identifier-dot chain of any depth (`option.hero.` / `line.`) followed by
 * one of FIELD_NAMES, OR the bare field name alone (a destructured local or
 * a loop variable named exactly after the field, e.g. `amount`).
 */
function buildFieldAccessPattern(): string {
  const alternation = FIELD_NAMES.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  return `(?:[A-Za-z_$][\\w$]*\\.)*(?:${alternation})\\b`;
}

function buildArithmeticRegex(): RegExp {
  const access = buildFieldAccessPattern();
  // `\)?`/`\(?` around the access lets this also catch a Number(...)-coerced
  // field sitting next to an operator (e.g. `Number(option.hero.rate) + 1`),
  // not just a bare/dotted access.
  return new RegExp(`(?:${access})\\)?\\s*[+\\-*/]|[+\\-*/]\\s*\\(?(?:${access})`);
}

const ARITHMETIC_ADJACENT_TO_FIELD = buildArithmeticRegex();

/** The single detector both the real file scan and the negative self-tests
 * below exercise -- returns the matched snippet, or null when clean. */
export function containsForbiddenArithmetic(source: string): string | null {
  const stripped = stripStringsAndComments(source);
  const match = stripped.match(ARITHMETIC_ADJACENT_TO_FIELD);
  return match ? match[0] : null;
}

describe("FIELD_NAMES derivation (self-check)", () => {
  it("collects at least the money/rate/percent leaf fields the review named", () => {
    // A representative subset from the review's own list -- proves the
    // dynamic derivation actually found them, not just that the set is
    // non-empty.
    for (const expected of [
      "rate",
      "points_pct",
      "points_amount",
      "down_payment_pct",
      "monthly_payment",
      "cash_to_close",
      "loan_amount",
      "amount",
      "gross_amount",
      "pitia",
      "dscr",
    ]) {
      expect(FIELD_NAMES).toContain(expected);
    }
  });

  it("excludes non-numeric leaf fields (labels, ids, dates, enums, booleans)", () => {
    for (const excluded of [
      "first_name",
      "property_label",
      "quote_id",
      "label",
      "prepared_at",
      "strategy",
      "recommended",
      "expired",
      "lo_note",
    ]) {
      expect(FIELD_NAMES).not.toContain(excluded);
    }
  });
});

describe("containsForbiddenArithmetic (detector self-tests, CQ-021 review M2)", () => {
  it("catches a dotted property access: option.rate - 1", () => {
    expect(containsForbiddenArithmetic("const x = option.rate - 1;")).not.toBeNull();
  });

  it("catches a destructured local: monthly_payment - cash_to_close", () => {
    const source = `
      const { monthly_payment, cash_to_close } = option.hero;
      const x = monthly_payment - cash_to_close;
    `;
    expect(containsForbiddenArithmetic(source)).not.toBeNull();
  });

  it("catches a loop variable: line.amount + other.amount", () => {
    const source = `
      for (const line of breakdown.payment_lines) {
        total = line.amount + other.amount;
      }
    `;
    expect(containsForbiddenArithmetic(source)).not.toBeNull();
  });

  it("catches Number()-coerced money values combined with +", () => {
    expect(containsForbiddenArithmetic("Number(option.hero.monthly_payment) + 1")).not.toBeNull();
  });

  it("does NOT flag index math: i + 1", () => {
    expect(containsForbiddenArithmetic("for (let i = 0; i < n; i = i + 1) {}")).toBeNull();
  });

  it("does NOT flag array/string index arithmetic unrelated to money fields", () => {
    expect(containsForbiddenArithmetic("const next = items[i + 1];")).toBeNull();
  });

  it("does NOT flag a plain function call or ternary on a money field", () => {
    const source = `
      formatMoney(option.hero.monthly_payment);
      const label = option.hero.loan_amount ? "shown" : "hidden";
    `;
    expect(containsForbiddenArithmetic(source)).toBeNull();
  });

  it("does NOT flag Tailwind classes or prose stripped as strings/comments", () => {
    const source = `
      // rate - 1 mentioned only in a comment, not real code
      const cls = "px-4 py-2 gap-1 text-status-danger";
    `;
    expect(containsForbiddenArithmetic(source)).toBeNull();
  });
});

describe("packages/ui/src/report never does arithmetic on money props (CQ-021 AC5)", () => {
  const files = readdirSync(REPORT_DIR).filter(isScannedFile);

  it("scans at least every component file this item owns", () => {
    // Guards against the scan silently covering zero files if this test
    // ever moves directories.
    expect(files.length).toBeGreaterThanOrEqual(10);
  });

  it("FIELD_NAMES is non-trivial (fixtures loaded correctly)", () => {
    expect(FIELD_NAMES.length).toBeGreaterThanOrEqual(15);
  });

  for (const file of files) {
    it(`${file} performs no arithmetic on ReportViewModel money/rate/percent fields`, () => {
      const match = containsForbiddenArithmetic(readFileSync(join(REPORT_DIR, file), "utf-8"));
      expect(match, `Found arithmetic near a money field in ${file}: ${match}`).toBeNull();
    });
  }
});
