import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type Tab = components["schemas"]["TabName"];
export type ApplyDraft = components["schemas"]["ApplyDraftOut"];
export type DraftPatchResponse = components["schemas"]["DraftPatchResponse"];
export type SubmitResponse = components["schemas"]["SubmitResponse"];
export type MetrosOut = components["schemas"]["MetrosOut"];
export type DraftDocument = components["schemas"]["DraftDocumentOut"];
export type DocType = DraftDocument["doc_type"];

export const TAB_ORDER: Tab[] = ["you", "property", "income", "consent"];

export const TAB_LABELS: Record<Tab, string> = {
  you: "You",
  property: "Property & goal",
  income: "Income & assets",
  consent: "Consent",
};

export const DOC_TYPE_OPTIONS: { value: DocType; label: string }[] = [
  { value: "pay_stub", label: "Pay stub" },
  { value: "w2", label: "W-2" },
  { value: "bank_statement", label: "Bank statement" },
];

export function createOrGetDraft() {
  return api.POST("/api/v1/portal/applications");
}

export function getDraft(draftId: string) {
  return api.GET("/api/v1/portal/applications/{draft_id}", {
    params: { path: { draft_id: draftId } },
  });
}

export function patchDraft(draftId: string, tab: Tab, data: Record<string, unknown>) {
  return api.PATCH("/api/v1/portal/applications/{draft_id}/draft", {
    params: { path: { draft_id: draftId } },
    body: { tab, data },
  });
}

export function listMetros() {
  return api.GET("/api/v1/portal/applications/metros");
}

export function submitDraft(draftId: string) {
  return api.POST("/api/v1/portal/applications/{draft_id}/submit", {
    params: { path: { draft_id: draftId } },
  });
}

// openapi-fetch's `defaultBodySerializer` special-cases `FormData` (passes
// it straight through so the browser sets `Content-Type`/boundary); the
// generated multipart schema type expects `{file: string, doc_type}`, so
// this cast is the standard openapi-fetch workaround for a File upload.
export function uploadDocument(draftId: string, file: File, docType: DocType) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("doc_type", docType);
  return api.POST("/api/v1/portal/applications/{draft_id}/documents", {
    params: { path: { draft_id: draftId } },
    body: formData as unknown as { file: string; doc_type: DocType },
  });
}

export function deleteDocument(draftId: string, documentId: string) {
  return api.DELETE("/api/v1/portal/applications/{draft_id}/documents/{document_id}", {
    params: { path: { draft_id: draftId, document_id: documentId } },
  });
}

export interface AppError {
  code?: string;
  message?: string;
  fieldErrors?: Record<string, Record<string, string>>;
  firstInvalidTab?: Tab;
  applicationId?: string;
}

/** The app-wide error envelope (`backend/app/core/errors.py`):
 * `{"error": {"code", "message", "details"}}`. Submit's `details` carries
 * `field_errors`/`first_invalid_tab` (422) or `application_id` (409); this
 * reads all of it defensively since openapi-fetch types these as
 * `unknown` (not documented per-status response shapes). */
export function parseAppError(error: unknown): AppError | null {
  if (typeof error !== "object" || error === null || !("error" in error)) return null;
  const inner = (error as { error?: unknown }).error;
  if (typeof inner !== "object" || inner === null) return null;
  const shaped = inner as { code?: unknown; message?: unknown; details?: unknown };
  const details =
    typeof shaped.details === "object" && shaped.details !== null
      ? (shaped.details as Record<string, unknown>)
      : {};
  return {
    code: typeof shaped.code === "string" ? shaped.code : undefined,
    message: typeof shaped.message === "string" ? shaped.message : undefined,
    fieldErrors: details.field_errors as Record<string, Record<string, string>> | undefined,
    firstInvalidTab: details.first_invalid_tab as Tab | undefined,
    applicationId: details.application_id as string | undefined,
  };
}
