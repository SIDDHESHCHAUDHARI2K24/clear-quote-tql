// AC5: "A static check fails the build if any file in
// packages/ui/src/report/ performs arithmetic on money props (lint rule or
// test that scans for `+ - * /` applied to those fields; document the
// approach in plan.md)." See CQ-021 plan.md Decision 4 for why this is a
// scan test rather than a custom eslint rule (no-code-scanning plugin was
// already wired into eslint.config.mjs, and a project-local rule would need
// its own package + build step for one check).
//
// Approach: for every *.tsx/*.ts source file in this directory (excluding
// tests, fixtures and this file's own two sanctioned formatters), strip
// string/template literals and comments (so Tailwind classes like "px-4"
// and JSDoc prose never produce false positives), then scan what's left for
// an arithmetic operator (`+ - * /`) directly adjacent to a `ReportViewModel`
// field-path access (`option.hero.monthly_payment`, `Number(...)`, etc.).
// This is a heuristic, not a full parser -- it is deliberately conservative
// (a few possible false negatives on deeply refactored code) in exchange for
// zero false positives against this directory's actual code today.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const REPORT_DIR = join(__dirname);
const ALLOWED_FILES = new Set(["format.ts", "types.ts"]);

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

// A money/rate/percent field-path access, e.g. `option.hero.monthly_payment`,
// `breakdown.payment_total`, `line.amount`, or a `Number(...)` coercion of one.
const FIELD_PATH =
  /\b\w+\.(hero|breakdown|cashflow|cost_seg|costSeg|payment_lines|cash_to_close_lines)\b[\w.]*|\bNumber\([^)]*\)/;

const ARITHMETIC_ADJACENT_TO_FIELD = new RegExp(
  `(${FIELD_PATH.source})\\s*[+\\-*/]\\s*\\w|\\w\\s*[+\\-*/]\\s*(${FIELD_PATH.source})`,
);

describe("packages/ui/src/report never does arithmetic on money props (CQ-021 AC5)", () => {
  const files = readdirSync(REPORT_DIR).filter(isScannedFile);

  it("scans at least every component file this item owns", () => {
    // Guards against the scan silently covering zero files if this test
    // ever moves directories.
    expect(files.length).toBeGreaterThanOrEqual(10);
  });

  for (const file of files) {
    it(`${file} performs no arithmetic on ReportViewModel money/rate/percent fields`, () => {
      const source = readFileSync(join(REPORT_DIR, file), "utf-8");
      const stripped = stripStringsAndComments(source);
      const match = stripped.match(ARITHMETIC_ADJACENT_TO_FIELD);
      expect(match, `Found arithmetic near a money field in ${file}: ${match?.[0]}`).toBeNull();
    });
  }
});
