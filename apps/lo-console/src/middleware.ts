import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { isPublicPath } from "@cq/ui";

// Cookie name mirrors backend/app/features/auth/sessions/service.py's
// COOKIE_NAMES["staff"] (plan.md Decision #7). This is a fast, unauthenticated
// pre-check only — presence doesn't mean the session is still valid; the
// `(staff)` route group's `StaffSessionProvider` (src/features/shell)
// authoritatively confirms via `GET /api/v1/auth/staff/me` and redirects
// back to /login on a 401.
const SESSION_COOKIE = "cq_staff_session";

const PUBLIC_PATHS = new Set(["/login", "/gallery", "/gallery/report"]);

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has(SESSION_COOKIE);

  if (hasSession && pathname === "/login") {
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
