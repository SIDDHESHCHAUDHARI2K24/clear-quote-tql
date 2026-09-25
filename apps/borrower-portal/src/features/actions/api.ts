import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type BorrowerActionType = components["schemas"]["BorrowerActionType"];
export type PortalReportActionResponse = components["schemas"]["PortalReportActionResponse"];

/** The parsed shape of `PortalReportResponse.borrower_action` / a version's
 * stored JSONB (`portal/actions/service.py::submit_action` -- `{type,
 * quote_id, message, at}`). The generated type is a loose `Record<string,
 * unknown>` since the column is JSONB; this is the shape this app actually
 * relies on. */
export interface BorrowerActionRecord {
  type: BorrowerActionType;
  quote_id: string | null;
  message: string | null;
  at: string;
}

export function parseBorrowerAction(
  value: Record<string, unknown> | null | undefined,
): BorrowerActionRecord | null {
  if (!value) return null;
  const { type, quote_id, message, at } = value;
  if (typeof type !== "string" || typeof at !== "string") return null;
  return {
    type: type as BorrowerActionType,
    quote_id: typeof quote_id === "string" ? quote_id : null,
    message: typeof message === "string" ? message : null,
    at,
  };
}

export async function submitReportAction(
  token: string,
  body: { type: BorrowerActionType; quote_id?: string; message?: string },
) {
  return api.POST("/api/v1/portal/reports/{token}/actions", {
    params: { path: { token } },
    body,
  });
}
