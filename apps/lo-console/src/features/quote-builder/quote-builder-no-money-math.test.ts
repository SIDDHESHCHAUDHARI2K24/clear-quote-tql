// AGENTS.md: "Money math lives only in quote_engine. Frontends never
// compute money." Reuses CQ-017's detector (`containsForbiddenArithmetic`,
// an arithmetic operator adjacent to a money/rate field name) over this
// feature's own files, with field names derived from this feature's own
// fixtures (real API responses: quote cards, scenario groups, product rows)
// plus the pricing panel's.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { FIELD_NAMES as PRICING_FIELD_NAMES } from "../pricing/pricing-no-money-math.test";

const FEATURE_DIR = join(__dirname);
const FIXTURES_DIR = join(__dirname, "__fixtures__");
// `api.ts`: type aliases and thin fetch wrappers only (no field arithmetic).
const ALLOWED_FILES = new Set(["api.ts"]);
const DECIMAL_STRING = /^-?\d+(\.\d+)?$/;

function collect(value: unknown, names: Set<string>, key?: string): void {
  if (Array.isArray(value)) {
    for (const item of value) collect(item, names);
    return;
  }
  if (value !== null && typeof value === "object") {
    for (const [k, v] of Object.entries(value)) collect(v, names, k);
    return;
  }
  if (typeof value === "string" && key && DECIMAL_STRING.test(value)) names.add(key);
}

function fieldNames(): string[] {
  const names = new Set<string>(PRICING_FIELD_NAMES);
  for (const file of readdirSync(FIXTURES_DIR)) {
    if (!file.endsWith(".json")) continue;
    collect(JSON.parse(readFileSync(join(FIXTURES_DIR, file), "utf-8")), names);
  }
  names.delete("value");
  names.delete("fico");
  return [...names].sort();
}

const NAMES = fieldNames();

function strip(source: string): string {
  return source
    .replace(/`(?:[^`\\]|\\.)*`/g, "``")
    .replace(/"(?:[^"\\]|\\.)*"/g, '""')
    .replace(/'(?:[^'\\]|\\.)*'/g, "''")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\n]*/g, "");
}

const ACCESS = `(?:[A-Za-z_$][\\w$]*\\.)*(?:${NAMES.map((n) =>
  n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
).join("|")})\\b`;
const ARITHMETIC = new RegExp(`(?:${ACCESS})\\)?\\s*[+\\-*/]|[+\\-*/]\\s*\\(?(?:${ACCESS})`);

function isScanned(name: string): boolean {
  return (
    /\.(ts|tsx)$/.test(name) &&
    !name.endsWith(".test.ts") &&
    !name.endsWith(".test.tsx") &&
    !ALLOWED_FILES.has(name)
  );
}

describe("features/quote-builder never does arithmetic on money/rate API fields", () => {
  const files = readdirSync(FEATURE_DIR).filter(isScanned);

  it("scans every component/hook file and knows the card's money fields", () => {
    expect(files.length).toBeGreaterThanOrEqual(8);
    for (const name of [
      "monthly_payment",
      "cash_to_close",
      "points_amount",
      "rate_pct",
      "points_pct",
      "monthly_cashflow",
      "dscr_ratio",
      "monthly_pi",
      "note_rate",
    ]) {
      expect(NAMES).toContain(name);
    }
  });

  it("the detector catches arithmetic next to a field (self-check)", () => {
    expect(strip("const x = quote.monthly_payment * 2;").match(ARITHMETIC)).not.toBeNull();
    expect(strip("const x = 1 - card.cash_to_close;").match(ARITHMETIC)).not.toBeNull();
  });

  for (const file of files) {
    it(`${file} performs no arithmetic on money/rate fields`, () => {
      const match = strip(readFileSync(join(FEATURE_DIR, file), "utf-8")).match(ARITHMETIC);
      expect(match?.[0] ?? null, `arithmetic near a money/rate field in ${file}`).toBeNull();
    });
  }
});
