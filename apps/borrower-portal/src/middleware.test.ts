import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { middleware } from "./middleware";

function requestFor(path: string, cookie?: string): NextRequest {
  const headers = new Headers();
  if (cookie) headers.set("cookie", `cq_borrower_session=${cookie}`);
  return new NextRequest(new URL(path, "http://localhost:3020"), { headers });
}

describe("middleware", () => {
  it("redirects to /login when there is no session cookie and the path is not public", () => {
    const response = middleware(requestFor("/"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost:3020/login");
  });

  it("lets an unauthenticated visitor reach /login", () => {
    const response = middleware(requestFor("/login"));

    expect(response.headers.get("location")).toBeNull();
  });

  it("lets an unauthenticated visitor reach /signup", () => {
    const response = middleware(requestFor("/signup"));

    expect(response.headers.get("location")).toBeNull();
  });

  it("lets an unauthenticated visitor reach /gallery", () => {
    const response = middleware(requestFor("/gallery"));

    expect(response.headers.get("location")).toBeNull();
  });

  it("redirects a signed-in visitor away from /login to /", () => {
    const response = middleware(requestFor("/login", "sess_123"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost:3020/");
  });

  it("redirects a signed-in visitor away from /signup to /", () => {
    const response = middleware(requestFor("/signup", "sess_123"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost:3020/");
  });

  it("lets a signed-in visitor through to /", () => {
    const response = middleware(requestFor("/", "sess_123"));

    expect(response.headers.get("location")).toBeNull();
  });
});
