import type { components } from "@cq/api-client";
import { extractErrorMessage } from "@cq/ui";

import { api } from "../../../lib/api-client";

// CQ-028a's verification-tab API (docs/backlog/CQ-028-verification-tabs/
// plan.md). Every write route returns the freshly rebuilt `SectionResponse`
// for the field/row's *owning* tab (fields.py `resolve_field` -- e.g.
// `occupancy_type` always resolves to the Property tab, regardless of which
// tab the LO edited it from) plus `resume`, set only on routes that go
// through the backend's re-verify/resume hook (field edits/reverts, row
// adds/edits, import-liabilities, property PATCH -- not SSN reveal, the
// hard-pull request or a document PATCH).

export type SectionTab = components["schemas"]["SectionTab"];
export type SectionResponse = components["schemas"]["SectionResponse"];
export type SectionRecord = components["schemas"]["SectionRecord"];
export type SectionField = components["schemas"]["SectionField"];
export type SectionFlag = components["schemas"]["SectionFlag"];
export type ResumeResult = components["schemas"]["ResumeResult"];
export type FieldSource = components["schemas"]["FieldSource"];
export type ConsentSummary = components["schemas"]["ConsentSummary"];
export type ConsentStatus = components["schemas"]["ConsentStatus"];
export type CreditSummary = components["schemas"]["CreditSummary"];
export type AssetsSummary = components["schemas"]["AssetsSummary"];
export type HousingSummary = components["schemas"]["HousingSummary"];
export type PropertySummary = components["schemas"]["PropertySummary"];
export type DocumentItem = components["schemas"]["DocumentItem"];
export type HardPullRequestResponse = components["schemas"]["HardPullRequestResponse"];
export type MetrosResponse = components["schemas"]["MetrosResponse"];
export type StateMetros = components["schemas"]["StateMetros"];
export type SsnRevealResponse = components["schemas"]["SsnRevealResponse"];
export type FieldEditValue = components["schemas"]["FieldEditRequest"]["value"];
export type HousingCreate = components["schemas"]["HousingCreate"];
export type HousingPatch = components["schemas"]["HousingPatch"];
export type PartyCreate = components["schemas"]["PartyCreate"];
export type PartyPatch = components["schemas"]["PartyPatch"];
export type LiabilityCreate = components["schemas"]["LiabilityCreate"];
export type LiabilityPatch = components["schemas"]["LiabilityPatch"];
export type PropertyPatch = components["schemas"]["PropertyPatch"];
export type AddressInput = components["schemas"]["AddressInput"];
export type PropertyType = components["schemas"]["PropertyType"];

export function fetchSection(applicationId: string, tab: SectionTab) {
  return api.GET("/api/v1/applications/{application_id}/sections/{tab}", {
    params: { path: { application_id: applicationId, tab } },
  });
}

export function putField(applicationId: string, fieldKey: string, value: FieldEditValue) {
  return api.PUT("/api/v1/applications/{application_id}/fields/{field_key}", {
    params: { path: { application_id: applicationId, field_key: fieldKey } },
    body: { value },
  });
}

export function revertField(applicationId: string, fieldKey: string) {
  return api.DELETE("/api/v1/applications/{application_id}/fields/{field_key}", {
    params: { path: { application_id: applicationId, field_key: fieldKey } },
  });
}

export function revealSsn(applicationId: string, partyId: string) {
  return api.POST("/api/v1/applications/{application_id}/parties/{party_id}/ssn-reveal", {
    params: { path: { application_id: applicationId, party_id: partyId } },
  });
}

export function addHousing(applicationId: string, body: HousingCreate) {
  return api.POST("/api/v1/applications/{application_id}/housing_history", {
    params: { path: { application_id: applicationId } },
    body,
  });
}

export function patchHousing(applicationId: string, rowId: string, body: HousingPatch) {
  return api.PATCH("/api/v1/applications/{application_id}/housing_history/{row_id}", {
    params: { path: { application_id: applicationId, row_id: rowId } },
    body,
  });
}

export function addParty(applicationId: string, body: PartyCreate) {
  return api.POST("/api/v1/applications/{application_id}/parties", {
    params: { path: { application_id: applicationId } },
    body,
  });
}

export function patchParty(applicationId: string, partyId: string, body: PartyPatch) {
  return api.PATCH("/api/v1/applications/{application_id}/parties/{party_id}", {
    params: { path: { application_id: applicationId, party_id: partyId } },
    body,
  });
}

export function addLiability(applicationId: string, body: LiabilityCreate) {
  return api.POST("/api/v1/applications/{application_id}/liabilities", {
    params: { path: { application_id: applicationId } },
    body,
  });
}

export function patchLiability(applicationId: string, rowId: string, body: LiabilityPatch) {
  return api.PATCH("/api/v1/applications/{application_id}/liabilities/{row_id}", {
    params: { path: { application_id: applicationId, row_id: rowId } },
    body,
  });
}

export function importLiabilities(applicationId: string) {
  return api.POST("/api/v1/applications/{application_id}/credit/import-liabilities", {
    params: { path: { application_id: applicationId } },
  });
}

export function requestHardPull(applicationId: string) {
  return api.POST("/api/v1/applications/{application_id}/credit/hard-pull-request", {
    params: { path: { application_id: applicationId } },
  });
}

export function patchProperty(applicationId: string, body: PropertyPatch) {
  return api.PATCH("/api/v1/applications/{application_id}/property", {
    params: { path: { application_id: applicationId } },
    body,
  });
}

export function patchDocument(applicationId: string, documentId: string, received: boolean) {
  return api.PATCH("/api/v1/applications/{application_id}/documents/{document_id}", {
    params: { path: { application_id: applicationId, document_id: documentId } },
    body: { received },
  });
}

export function fetchMetros(states: string[]) {
  return api.GET("/api/v1/reference/metros", {
    params: { query: { states: states.join(",") } },
  });
}

/** Every section write's `{data, error}` shape collapses to this: either the
 * refreshed section, or a message from the backend's own error envelope /
 * FastAPI 422 body (never a raw `unknown`, per `@cq/ui`'s `extractErrorMessage`). */
export type SectionActionResult =
  { ok: true; section: SectionResponse } | { ok: false; message: string };

/** Finds a row record's field by its column suffix (the real `field_key` is
 * `{collection}.{row_id}.{suffix}`) -- shared by every tab that renders
 * fixed-order row fields (Housing, Credit's liabilities, Assets' assets and
 * employment), instead of each tab redefining the same lookup
 * (code-review finding: 3 byte-for-byte copies). */
export function fieldBySuffix(record: SectionRecord, suffix: string): SectionField | undefined {
  return record.fields.find((field) => field.field_key.endsWith(`.${suffix}`));
}

export async function runSectionAction(
  call: () => Promise<{ data?: SectionResponse; error?: unknown }>,
  fallback = "Could not save. Try again.",
): Promise<SectionActionResult> {
  try {
    const { data, error } = await call();
    if (data) return { ok: true, section: data };
    return { ok: false, message: extractErrorMessage(error, fallback) };
  } catch {
    return { ok: false, message: "Network error. Try again." };
  }
}
