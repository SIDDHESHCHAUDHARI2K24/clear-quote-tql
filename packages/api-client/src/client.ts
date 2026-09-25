import createClient from "openapi-fetch";

import type { paths } from "./schema";

export function createApiClient(baseUrl: string) {
  // Staff/borrower sessions (CQ-014/CQ-015) are httpOnly cookies set by the
  // API; the browser only sends/receives them on same-origin-credentialed
  // requests. `same-origin` (fetch's default) drops the cookie on the
  // console's own cross-port calls to the API in local dev (localhost:3010
  // -> localhost:8012), so every client the app makes must opt in.
  return createClient<paths>({ baseUrl, credentials: "include" });
}

export type ApiClient = ReturnType<typeof createApiClient>;
