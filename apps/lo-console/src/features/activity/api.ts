import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type ActivityEvent = components["schemas"]["ActivityEventOut"];
export type ActivityPage = components["schemas"]["Page_ActivityEventOut_"];

export async function fetchActivity(applicationId: string, page: number) {
  return api.GET("/api/v1/applications/{application_id}/activity", {
    params: { path: { application_id: applicationId }, query: { page } },
  });
}
