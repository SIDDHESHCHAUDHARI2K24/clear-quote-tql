import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { isPublicPath } from "@cq/ui";

// Cookie name mirrors backend/app/features/auth/sessions/service.py's
// COOKIE_NAMES["borrower"] (plan.md Decision #9). This is a fast,
// unauthenticated pre-check only — presence doesn't mean the session is
// still valid; the `(portal)` route group's `BorrowerSessionProvider` authoritatively
// confirms via `GET /api/v1/auth/borrower/me` and redirects back to /login
// on a 401.
const SESSION_COOKIE = "cq_borrower_session";

const PUBLIC_PATHS = new Set(["/login", "/signup", "/gallery", "/gallery/report"]);

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has(SESSION_COOKIE);

  if (hasSession && (pathname === "/login" || pathname === "/signup")) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  if (!hasSession && !isPublicPath(pathname, PUBLIC_PATHS)) {
    const loginUrl = new URL("/login", request.url);
    // H2 (docs/backlog/phase-p3-p4-plan.md): a signed-out visit to a
    // protected path (e.g. `/report/{token}`) redirects to
    // `/login?next=<path>` so OTP success can return here (`nextParam.ts`
    // validates this on the way back out -- middleware itself only ever
    // builds `next` from the request's own same-origin pathname/search, so
    // nothing unsafe originates here). `/` is the default post-login
    // destination already, so it's left off to keep the common case's URL
    // (and this file's existing tests) unchanged.
    if (pathname !== "/") {
      loginUrl.searchParams.set("next", pathname + request.nextUrl.search);
    }
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
