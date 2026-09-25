import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type PortalHomeResponse = components["schemas"]["PortalHomeResponse"];
export type PortalApplicationOut = components["schemas"]["PortalApplicationOut"];
export type PortalNextAction = components["schemas"]["PortalNextAction"];
export type PortalStage = components["schemas"]["PortalStage"];
export type PortalNextActionType = components["schemas"]["PortalNextActionType"];

/** `GET /api/v1/portal/me` (CQ-031 spec.md). */
export function fetchPortalHome() {
  return api.GET("/api/v1/portal/me");
}
