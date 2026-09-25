import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { isPublicPath } from "@cq/ui";

// Cookie name mirrors backend/app/features/auth/sessions/service.py's
// COOKIE_NAMES["borrower"] (plan.md Decision #9). This is a fast,
// unauthenticated pre-check only — presence doesn't mean the session is
// still valid; the signed-in home page (`src/app/page.tsx`) authoritatively
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
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
