import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type DashboardResponse = components["schemas"]["DashboardResponse"];
export type DashboardTiles = components["schemas"]["DashboardTiles"];
export type AttentionItem = components["schemas"]["AttentionItem"];
export type StaleItem = components["schemas"]["StaleItem"];
export type ActivityItem = components["schemas"]["ActivityItem"];
export type LoOption = components["schemas"]["LoOption"];

export async function fetchDashboard(loId?: string) {
  return api.GET("/api/v1/dashboard", {
    params: { query: { lo_id: loId } },
  });
}
