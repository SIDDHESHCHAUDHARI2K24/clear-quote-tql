import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type DashboardResponse = components["schemas"]["DashboardResponse"];
export type DashboardTiles = components["schemas"]["DashboardTiles"];
export type AttentionItem = components["schemas"]["AttentionItem"];
export type StaleItem = components["schemas"]["StaleItem"];
export type ActivityItem = components["schemas"]["ActivityItem"];
// `DashboardLoOption`, not the bare `LoOption` -- CQ-027's own
// `applications.listing.schemas.LoOption` FastAPI schema has that name;
// the backend renamed this one to avoid an `openapi-typescript` component
// collision once both routers are mounted (CQ-025 fix).
export type LoOption = components["schemas"]["DashboardLoOption"];

export async function fetchDashboard(loId?: string) {
  return api.GET("/api/v1/dashboard", {
    params: { query: { lo_id: loId } },
  });
}
