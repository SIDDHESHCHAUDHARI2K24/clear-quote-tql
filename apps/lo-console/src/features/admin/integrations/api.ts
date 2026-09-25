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

/** CQ-030's `POST /admin/jobs/stale-check` lands separately in this wave.
 * openapi-fetch's generated `paths` type has no runtime representation (it
 * disappears at compile time), so there's nothing to introspect at
 * runtime; per plan.md decision 8 this is the logged constant-flag
 * fallback instead. CQ-030 (or the orchestrator's merge) flips this to
 * `true` once `PUT /api/v1/admin/jobs/stale-check` actually exists. */
export const STALE_CHECK_JOB_AVAILABLE = false;
