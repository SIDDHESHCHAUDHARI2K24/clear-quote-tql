import createClient from "openapi-fetch";

import type { paths } from "./schema";

export function createApiClient(baseUrl: string) {
  return createClient<paths>({ baseUrl });
}

export type ApiClient = ReturnType<typeof createApiClient>;
