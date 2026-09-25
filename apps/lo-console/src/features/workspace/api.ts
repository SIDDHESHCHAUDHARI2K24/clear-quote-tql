import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type ApplicationSummary = components["schemas"]["ApplicationSummaryResponse"];
export type TabState = components["schemas"]["TabStateResponse"];
export type ApplicationTab = components["schemas"]["ApplicationTab"];
export type StatusPatchStatus = components["schemas"]["StatusPatchRequest"]["status"];

export async function fetchApplicationSummary(applicationId: string) {
  return api.GET("/api/v1/applications/{application_id}/summary", {
    params: { path: { application_id: applicationId } },
  });
}

export async function patchApplicationStatus(
  applicationId: string,
  status: StatusPatchStatus,
  reason: string,
) {
  return api.PATCH("/api/v1/applications/{application_id}/status", {
    params: { path: { application_id: applicationId } },
    body: { status, reason: reason.length > 0 ? reason : null },
  });
}
