import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type PortalConsent = components["schemas"]["PortalConsentOut"];

/** `GET /api/v1/portal/consents/{id}` (CQ-033). */
export function fetchConsent(consentId: string) {
  return api.GET("/api/v1/portal/consents/{consent_id}", {
    params: { path: { consent_id: consentId } },
  });
}

/** `POST /api/v1/portal/consents/{id}/accept` — records the signed decision
 * and runs the hard pull server-side. */
export function acceptConsent(consentId: string, typedName: string) {
  return api.POST("/api/v1/portal/consents/{consent_id}/accept", {
    params: { path: { consent_id: consentId } },
    body: { typed_name: typedName },
  });
}

/** `POST /api/v1/portal/consents/{id}/decline` with an optional reason. */
export function declineConsent(consentId: string, reason: string) {
  return api.POST("/api/v1/portal/consents/{consent_id}/decline", {
    params: { path: { consent_id: consentId } },
    body: { reason: reason.trim() ? reason.trim() : null },
  });
}
