import type { paths } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type ApplicationListQuery = NonNullable<
  paths["/api/v1/applications"]["get"]["parameters"]["query"]
>;

export async function fetchApplications(query: ApplicationListQuery) {
  return api.GET("/api/v1/applications", { params: { query } });
}

export async function fetchLoOptions() {
  return api.GET("/api/v1/applications/los");
}
