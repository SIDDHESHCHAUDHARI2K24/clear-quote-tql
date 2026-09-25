import { describe, expect, it } from "vitest";

import { isPublicPath, STATIC_ASSET_PATTERN } from "./paths";

describe("isPublicPath", () => {
  const LO_PUBLIC_PATHS = new Set(["/login", "/gallery"]);
  const BORROWER_PUBLIC_PATHS = new Set(["/login", "/signup", "/gallery"]);

  it("treats a listed path as public", () => {
    expect(isPublicPath("/login", LO_PUBLIC_PATHS)).toBe(true);
    expect(isPublicPath("/gallery", LO_PUBLIC_PATHS)).toBe(true);
  });

  it("treats an unlisted path as not public", () => {
    expect(isPublicPath("/", LO_PUBLIC_PATHS)).toBe(false);
    expect(isPublicPath("/signup", LO_PUBLIC_PATHS)).toBe(false);
  });

  it("supports a public-path set that differs per app (borrower portal adds /signup)", () => {
    expect(isPublicPath("/signup", BORROWER_PUBLIC_PATHS)).toBe(true);
  });

  it("accepts a plain array as well as a Set", () => {
    expect(isPublicPath("/login", ["/login", "/gallery"])).toBe(true);
    expect(isPublicPath("/other", ["/login", "/gallery"])).toBe(false);
  });

  it("treats any /_next/ path as public", () => {
    expect(isPublicPath("/_next/static/chunk.js", LO_PUBLIC_PATHS)).toBe(true);
  });

  it("treats any path with a file extension as a public static asset", () => {
    expect(isPublicPath("/favicon.ico", LO_PUBLIC_PATHS)).toBe(true);
    expect(isPublicPath("/logo.png", LO_PUBLIC_PATHS)).toBe(true);
  });
});

describe("STATIC_ASSET_PATTERN", () => {
  it("matches a path with a file extension", () => {
    expect(STATIC_ASSET_PATTERN.test("/favicon.ico")).toBe(true);
  });

  it("does not match a route with no extension", () => {
    expect(STATIC_ASSET_PATTERN.test("/dashboard")).toBe(false);
  });
});
