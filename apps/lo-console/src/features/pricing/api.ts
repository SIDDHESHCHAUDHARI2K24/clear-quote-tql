import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type PricingView = components["schemas"]["PricingViewResponse"];
export type PricingField = components["schemas"]["PricingFieldView"];
export type PricingInputs = components["schemas"]["PricingInputsView"];
export type QuoteComputation = components["schemas"]["QuoteComputation"];
export type QuotePreviewRequest = components["schemas"]["QuotePreviewRequest"];
export type QuotePreviewResponse = components["schemas"]["QuotePreviewResponse"];
export type FieldSource = components["schemas"]["FieldSource"];
export type StrategyType = components["schemas"]["StrategyType"];

export async function fetchPricingView(applicationId: string) {
  return api.GET("/api/v1/applications/{application_id}/pricing", {
    params: { path: { application_id: applicationId } },
  });
}

export async function patchFieldValueOverride(
  applicationId: string,
  fieldKey: string,
  value: string,
) {
  return api.PATCH("/api/v1/applications/{application_id}/field-values/{field_key}", {
    params: { path: { application_id: applicationId, field_key: fieldKey } },
    body: { value },
  });
}

export async function revertFieldValue(applicationId: string, fieldKey: string) {
  return api.POST("/api/v1/applications/{application_id}/field-values/{field_key}/revert", {
    params: { path: { application_id: applicationId, field_key: fieldKey } },
  });
}

// `signal` lets the caller (usePricingPreview) abort a superseded request so
// an out-of-order response never overwrites a newer one.
export async function previewQuote(request: QuotePreviewRequest, signal?: AbortSignal) {
  return api.POST("/api/v1/quotes/preview", {
    body: request,
    signal,
  });
}
