// Pure helpers shared by both apps' `middleware.ts`. This package must not
// depend on `next` (middleware.ts stays app-owned so it can import
// `next/server`'s `NextResponse`/`NextRequest`), so these take and return
// plain strings only.

export const STATIC_ASSET_PATTERN = /\.[a-zA-Z0-9]+$/;

export function isPublicPath(
  pathname: string,
  publicPaths: ReadonlySet<string> | readonly string[],
): boolean {
  const set = publicPaths instanceof Set ? publicPaths : new Set(publicPaths);
  if (set.has(pathname)) return true;
  if (pathname.startsWith("/_next/")) return true;
  if (STATIC_ASSET_PATTERN.test(pathname)) return true;
  return false;
}
