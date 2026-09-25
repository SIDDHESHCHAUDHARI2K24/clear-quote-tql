import type { components } from "@cq/api-client";

import { api } from "../../../lib/api-client";

export type AdapterStatus = components["schemas"]["AdapterStatus"];

export async function fetchIntegrations() {
  return api.GET("/api/v1/admin/integrations");
}

export async function putIntegrationForceFailure(adapter: string, forceFailure: boolean) {
  return api.PUT("/api/v1/admin/integrations/{adapter}", {
    params: { path: { adapter } },
    body: { force_failure: forceFailure },
  });
}

export type StaleCheckResult = components["schemas"]["StaleCheckResponse"];

/** CQ-030's stale job, run in-process now instead of waiting for its
 * scheduled Temporal activity (plan.md decision 8 -- the button was
 * hidden behind a flag until this endpoint existed; CQ-030 has since
 * merged). Admin only; other roles get 403 (E16). */
export async function runStaleCheckNow() {
  return api.POST("/api/v1/admin/jobs/stale-check");
}
