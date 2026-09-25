import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type OutboxEmailRow = components["schemas"]["OutboxEmailRow"];
export type OutboxEmailDetail = components["schemas"]["OutboxEmailDetail"];

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface OutboxListParams {
  q?: string;
  type?: string;
  applicationId?: string;
  page?: number;
}

export async function fetchOutboxList(params: OutboxListParams) {
  return api.GET("/api/v1/outbox", {
    params: {
      query: {
        q: params.q || null,
        type: params.type || null,
        application_id: params.applicationId || null,
        page: params.page ?? 1,
      },
    },
  });
}

export async function fetchOutboxDetail(emailId: string) {
  return api.GET("/api/v1/outbox/{email_id}", {
    params: { path: { email_id: emailId } },
  });
}

/** The attachment route streams a raw file, not JSON -- a plain link href,
 * not the typed `api` client (spec.md: "detail view ... attachment
 * downloads"). Staff auth cookie rides along on the same-site request. */
export function attachmentDownloadUrl(emailId: string, key: string): string {
  // Encode each path segment but keep the `/`s literal -- the backend
  // route uses FastAPI's `{key:path}` converter, which expects a real
  // slash-separated path, not a `%2F`-escaped one.
  const encodedKey = key.split("/").map(encodeURIComponent).join("/");
  return `${API_BASE_URL}/api/v1/outbox/${emailId}/attachments/${encodedKey}`;
}
