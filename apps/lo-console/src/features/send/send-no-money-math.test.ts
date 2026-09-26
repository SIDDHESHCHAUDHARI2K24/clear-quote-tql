// AGENTS.md: "Money math lives only in quote_engine. Frontends never
// compute money." Same detector as the quote builder's
// (`quote-builder-no-money-math.test.ts`): an arithmetic operator next to a
// money/rate field name. Field names come from the pricing panel, the
// quote-builder fixtures (the cards this tab lists), this feature's own
// fixtures, and the report view model the preview renders. Recurses into
// subfolders and also catches compound assignment (`+=`, CQ-018 follow-up).
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import { REPORT_FIXTURES } from "@cq/ui";

import { FIELD_NAMES as PRICING_FIELD_NAMES } from "../pricing/pricing-no-money-math.test";

const FEATURE_DIR = join(__dirname);
const FIXTURE_DIRS = [
  join(__dirname, "__fixtures__"),
  join(__dirname, "../quote-builder/__fixtures__"),
];
// `api.ts`: type aliases and thin fetch wrappers only.
const ALLOWED_FILES = new Set(["api.ts"]);
const DECIMAL_STRING = /^-?\$?\d[\d,]*(\.\d+)?%?$/;

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
  for (const dir of FIXTURE_DIRS) {
    for (const file of readdirSync(dir)) {
      if (file.endsWith(".json"))
        collect(JSON.parse(readFileSync(join(dir, file), "utf-8")), names);
    }
  }
  for (const fixture of REPORT_FIXTURES) collect(fixture.viewModel, names);
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
const ARITHMETIC = new RegExp(
  `(?:${ACCESS})\\)?\\s*[+\\-*/]|[+\\-*/]=?\\s*\\(?(?:Number\\()?(?:${ACCESS})`,
);

function scannedFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "__fixtures__" ? [] : scannedFiles(path);
    const scanned =
      /\.(ts|tsx)$/.test(name) &&
      !name.endsWith(".test.ts") &&
      !name.endsWith(".test.tsx") &&
      !ALLOWED_FILES.has(name);
    return scanned ? [path] : [];
  });
}

describe("features/send never does arithmetic on money/rate API fields", () => {
  const files = scannedFiles(FEATURE_DIR);

  it("scans every component/hook file and knows the money fields", () => {
    expect(files.length).toBeGreaterThanOrEqual(8);
    for (const name of ["monthly_payment", "cash_to_close", "rate_pct", "purchase_price"]) {
      expect(NAMES).toContain(name);
    }
  });

  it("the detector catches arithmetic next to a field (self-check)", () => {
    expect(strip("const x = quote.monthly_payment * 2;").match(ARITHMETIC)).not.toBeNull();
    expect(strip("total += Number(card.cash_to_close);").match(ARITHMETIC)).not.toBeNull();
    expect(strip("const x = formatMoneyCents(card.cash_to_close);").match(ARITHMETIC)).toBeNull();
  });

  for (const file of files) {
    const name = relative(FEATURE_DIR, file);
    it(`${name} performs no arithmetic on money/rate fields`, () => {
      const match = strip(readFileSync(file, "utf-8")).match(ARITHMETIC);
      expect(match?.[0] ?? null, `arithmetic near a money/rate field in ${name}`).toBeNull();
    });
  }
});
