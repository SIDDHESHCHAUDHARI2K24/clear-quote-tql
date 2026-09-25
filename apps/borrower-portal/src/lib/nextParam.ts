/**
 * Validates a `?next=` redirect target (CQ-022, H2's "no magic link" flow:
 * a signed-out visit to `/report/{token}` redirects to `/login?next=/report/
 * {token}`, and OTP success returns to `next`). Only same-origin relative
 * paths starting with `/` and not `//` are accepted -- `next` is an
 * attacker-controlled query parameter, and a browser treats `//evil.com`
 * (or a value starting with a backslash, which some browsers normalize the
 * same way) as protocol-relative, navigating off-site. Anything else falls
 * back to `DEFAULT_NEXT_PATH`.
 *
 * Fresh-subagent review finding (fixed): a value containing a tab, CR or LF
 * anywhere (not just as a prefix) -- e.g. `"/\t/evil.com"` -- passed the
 * `//`/`/\\`-prefix checks above unchanged, but the WHATWG URL parser
 * removes every ASCII tab/newline from the input *before* parsing the
 * scheme/authority (https://url.spec.whatwg.org/#url-parsing), so
 * `new URL("/\t/evil.com", origin).href` resolves off-site exactly like a
 * literal `"//evil.com"` would -- confirmed live in Node. Rejecting any
 * occurrence of `\t`/`\r`/`\n` closes that gap before the prefix checks run.
 */
export const DEFAULT_NEXT_PATH = "/";

const CONTAINS_TAB_OR_NEWLINE = /[\t\r\n]/;

export function safeNextPath(next: string | null | undefined): string | null {
  if (!next) return null;
  if (CONTAINS_TAB_OR_NEWLINE.test(next)) return null;
  if (!next.startsWith("/")) return null;
  if (next.startsWith("//")) return null;
  if (next.startsWith("/\\")) return null;
  return next;
}

/** `safeNextPath`, falling back to `DEFAULT_NEXT_PATH` when `next` is
 * missing or unsafe -- what callers that always need a path (not `null`)
 * use. */
export function resolveNextPath(next: string | null | undefined): string {
  return safeNextPath(next) ?? DEFAULT_NEXT_PATH;
}
