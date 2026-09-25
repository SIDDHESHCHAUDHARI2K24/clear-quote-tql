import { describe, expect, it } from "vitest";

import { DEFAULT_NEXT_PATH, resolveNextPath, safeNextPath } from "./nextParam";

describe("safeNextPath", () => {
  it("accepts a same-origin relative path", () => {
    expect(safeNextPath("/report/abc123")).toBe("/report/abc123");
  });

  it("accepts a same-origin relative path with a query string", () => {
    expect(safeNextPath("/report/abc123?option=xyz")).toBe("/report/abc123?option=xyz");
  });

  it("rejects null/undefined/empty", () => {
    expect(safeNextPath(null)).toBeNull();
    expect(safeNextPath(undefined)).toBeNull();
    expect(safeNextPath("")).toBeNull();
  });

  it("rejects a protocol-relative URL (//evil.com)", () => {
    expect(safeNextPath("//evil.com")).toBeNull();
  });

  it("rejects an absolute URL with a scheme", () => {
    expect(safeNextPath("https://evil.com")).toBeNull();
    expect(safeNextPath("javascript:alert(1)")).toBeNull();
  });

  it("rejects a path not starting with /", () => {
    expect(safeNextPath("report/abc")).toBeNull();
  });

  it("rejects a backslash-prefixed path some browsers normalize to protocol-relative", () => {
    expect(safeNextPath("/\\evil.com")).toBeNull();
  });

  it("rejects a tab/CR/LF-embedded path the WHATWG URL parser strips into //evil.com (fresh-review finding)", () => {
    // https://url.spec.whatwg.org/#url-parsing removes every ASCII tab and
    // newline from the input before scheme/authority parsing, so each of
    // these becomes literally "//evil.com" once resolved by `new URL(...)`
    // -- verified: `new URL("/\t/evil.com", "https://portal.example/").href`
    // is `"https://evil.com/"`.
    expect(safeNextPath("/\t/evil.com")).toBeNull();
    expect(safeNextPath("/\n/evil.com")).toBeNull();
    expect(safeNextPath("/\r/evil.com")).toBeNull();
    expect(safeNextPath("/report/abc\t123")).toBeNull();
  });
});

describe("resolveNextPath", () => {
  it("returns the safe path when valid", () => {
    expect(resolveNextPath("/report/abc123")).toBe("/report/abc123");
  });

  it("falls back to the default path when unsafe", () => {
    expect(resolveNextPath("//evil.com")).toBe(DEFAULT_NEXT_PATH);
  });

  it("falls back to the default path when missing", () => {
    expect(resolveNextPath(null)).toBe(DEFAULT_NEXT_PATH);
    expect(resolveNextPath(undefined)).toBe(DEFAULT_NEXT_PATH);
  });
});
