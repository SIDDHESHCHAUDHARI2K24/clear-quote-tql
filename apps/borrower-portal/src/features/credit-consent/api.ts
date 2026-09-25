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
 * and runs the hard pull server-side. Echoes the version and SHA-256 of the
 * text the borrower was shown, so the stored hash proves what they saw
 * (409 `CONSENT_TEXT_CHANGED` if it no longer matches). */
export function acceptConsent(
  consentId: string,
  typedName: string,
  text: Pick<PortalConsent["text"], "version" | "sha256">,
) {
  return api.POST("/api/v1/portal/consents/{consent_id}/accept", {
    params: { path: { consent_id: consentId } },
    body: { typed_name: typedName, text_version: text.version, text_sha256: text.sha256 },
  });
}

/** `POST /api/v1/portal/consents/{id}/decline` with an optional reason. */
export function declineConsent(consentId: string, reason: string) {
  return api.POST("/api/v1/portal/consents/{consent_id}/decline", {
    params: { path: { consent_id: consentId } },
    body: { reason: reason.trim() ? reason.trim() : null },
  });
}
