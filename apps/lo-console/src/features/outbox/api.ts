import type { components } from "@cq/api-client";

import { API_BASE_URL, api } from "../../lib/api-client";

export type OutboxEmailRow = components["schemas"]["OutboxEmailRow"];
export type OutboxEmailDetail = components["schemas"]["OutboxEmailDetail"];

export { API_BASE_URL };

// Mirrors the backend's `EmailType` (notifications/outbox/schemas.py) --
// the `?type=` query param is now a FastAPI `Literal` of these four values
// (an unknown value is a 422, review round 1 minor 5), but the `Select`
// filter (OutboxList.tsx) works with a plain string (its `onChange` comes
// from a raw `<select>` element), so `OutboxListParams.type` stays `string`
// and is narrowed at this one call site instead.
export type EmailType = "otp" | "borrower_action" | "quote_sent" | "other";

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
        type: (params.type || null) as EmailType | null,
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
