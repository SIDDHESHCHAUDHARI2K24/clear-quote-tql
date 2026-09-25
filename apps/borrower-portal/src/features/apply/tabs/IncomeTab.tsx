"use client";

import { useId, useState } from "react";
import type { ChangeEvent } from "react";

import { Button, Select, extractErrorMessage } from "@cq/ui";

import type { DocType, DraftDocument } from "../api";
import { DOC_TYPE_OPTIONS, deleteDocument, uploadDocument } from "../api";
import { Field } from "../fields";
import { getString } from "../paths";
import type { TabFormProps } from "./TabForm";

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXTENSIONS = ["pdf", "jpg", "jpeg", "png"];
const MSG_TOO_LARGE = "Files must be 10 MB or smaller.";
const MSG_BAD_TYPE = "Only PDF, JPG and PNG files are accepted.";
const GENERIC_UPLOAD_ERROR = "Could not upload the file.";

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot === -1 ? "" : filename.slice(dot + 1).toLowerCase();
}

function documentsOf(data: TabFormProps["data"]): DraftDocument[] {
  const raw = data.documents;
  return Array.isArray(raw) ? (raw as DraftDocument[]) : [];
}

interface DocumentListProps {
  documents: DraftDocument[];
  disabled: boolean;
  onDelete: (id: string) => void;
}

/** The already-uploaded documents, each removable (split out of
 * `IncomeTab` for react-doctor `no-high-complexity-react-function`). */
function DocumentList({ documents, disabled, onDelete }: DocumentListProps) {
  if (documents.length === 0) {
    return <p className="text-sm text-neutral-600">No documents uploaded yet.</p>;
  }
  const labelFor = (docType: DocType) =>
    DOC_TYPE_OPTIONS.find((option) => option.value === docType)?.label ?? docType;
  return (
    <ul className="flex flex-col gap-2">
      {documents.map((doc) => (
        <li
          key={doc.id}
          className="flex items-center justify-between gap-3 rounded-md border border-neutral-200 px-3 py-2 text-sm"
        >
          <span className="text-navy-900">
            {labelFor(doc.doc_type)}: {doc.filename}
          </span>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onDelete(doc.id)}
            className="text-status-danger underline disabled:opacity-50"
          >
            Remove
          </button>
        </li>
      ))}
    </ul>
  );
}

export interface IncomeTabProps extends TabFormProps {
  draftId: string;
  /** Tab 2's occupancy, for the "required for primary" hint (the server
   * is the actual source of truth for which fields are required). */
  occupancy: string;
}

/** Tab 3 (spec.md table): income (required for a primary residence),
 * liquid assets (required for everyone), and optional document uploads.
 * Documents are server-managed (plan.md "Per-tab data contract": `income.
 * documents` is filled by the upload endpoint and ignored on PATCH), so
 * an upload/delete writes the new list through `set()` -- like any other
 * field -- rather than a separate local state: that keeps `data.
 * documents` (what a tab switch's remount re-seeds from) always current,
 * and the next autosave's response refreshes it from the server's own
 * list anyway (code review: a separate `useState` here went stale across
 * a remount because nothing propagated it back up to `ApplyWizard`). */
export function IncomeTab({ data, set, errorFor, disabled, draftId, occupancy }: IncomeTabProps) {
  const isPrimary = occupancy === "primary";
  const documents = documentsOf(data);
  const [docType, setDocType] = useState<DocType>("pay_stub");
  const [file, setFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputId = useId();

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] ?? null;
    setUploadError(null);
    setFile(next);
  }

  async function handleUpload() {
    if (!file) return;
    if (file.size === 0) {
      setUploadError("The file is empty.");
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setUploadError(MSG_TOO_LARGE);
      return;
    }
    if (!ALLOWED_EXTENSIONS.includes(extensionOf(file.name))) {
      setUploadError(MSG_BAD_TYPE);
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const { data: uploaded, error } = await uploadDocument(draftId, file, docType);
      if (!uploaded) {
        setUploadError(extractErrorMessage(error, GENERIC_UPLOAD_ERROR));
        return;
      }
      set("documents", [...documents, uploaded], "documents");
      setFile(null);
      const input = document.getElementById(fileInputId) as HTMLInputElement | null;
      if (input) input.value = "";
    } catch {
      setUploadError(GENERIC_UPLOAD_ERROR);
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(documentId: string) {
    const { response } = await deleteDocument(draftId, documentId);
    if (response.ok) {
      set(
        "documents",
        documents.filter((doc) => doc.id !== documentId),
        "documents",
      );
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold text-navy-900">Income</h2>
        {isPrimary && (
          <p className="text-sm text-neutral-600">
            Required since this will be the home you live in.
          </p>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field
            id="employer-name"
            label={isPrimary ? "Employer" : "Employer (optional)"}
            value={getString(data, "employer_name")}
            disabled={disabled}
            onChange={(e) => set("employer_name", e.target.value, "employer_name")}
            error={errorFor("employer_name")}
          />
          <Field
            id="years-employed"
            label={isPrimary ? "Years employed" : "Years employed (optional)"}
            inputMode="decimal"
            value={getString(data, "years_employed")}
            disabled={disabled}
            onChange={(e) => set("years_employed", e.target.value, "years_employed")}
            error={errorFor("years_employed")}
          />
          <Field
            id="monthly-income"
            label={isPrimary ? "Monthly gross income" : "Monthly gross income (optional)"}
            inputMode="decimal"
            value={getString(data, "monthly_income")}
            disabled={disabled}
            onChange={(e) => set("monthly_income", e.target.value, "monthly_income")}
            error={errorFor("monthly_income")}
          />
          <Field
            id="monthly-debts"
            label={isPrimary ? "Monthly debts" : "Monthly debts (optional)"}
            inputMode="decimal"
            value={getString(data, "monthly_debts")}
            disabled={disabled}
            onChange={(e) => set("monthly_debts", e.target.value, "monthly_debts")}
            error={errorFor("monthly_debts")}
          />
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h3 className="text-md font-semibold text-navy-900">Assets</h3>
        <Field
          id="liquid-assets"
          label="Liquid assets"
          inputMode="decimal"
          className="sm:max-w-xs"
          value={getString(data, "liquid_assets")}
          disabled={disabled}
          onChange={(e) => set("liquid_assets", e.target.value, "liquid_assets")}
          error={errorFor("liquid_assets")}
        />
      </section>

      <section className="flex flex-col gap-3">
        <h3 className="text-md font-semibold text-navy-900">Documents (optional)</h3>
        <p className="text-sm text-neutral-600">
          Pay stubs, W-2s or bank statements. PDF, JPG or PNG, 10 MB or less.
        </p>
        <DocumentList documents={documents} disabled={disabled} onDelete={handleDelete} />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <Select
            id="doc-type"
            label="Document type"
            options={DOC_TYPE_OPTIONS}
            value={docType}
            disabled={disabled || uploading}
            onChange={(value) => setDocType(value as DocType)}
          />
          <div className="flex flex-col gap-1">
            <label htmlFor={fileInputId} className="text-sm font-medium text-navy-900">
              File
            </label>
            <input
              id={fileInputId}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png"
              disabled={disabled || uploading}
              onChange={onFileChange}
              aria-describedby={uploadError ? `${fileInputId}-error` : undefined}
              aria-invalid={uploadError ? true : undefined}
            />
          </div>
          <Button
            type="button"
            variant="secondary"
            disabled={disabled || uploading || !file}
            isLoading={uploading}
            onClick={() => void handleUpload()}
          >
            Upload
          </Button>
        </div>
        {uploadError && (
          <p id={`${fileInputId}-error`} role="alert" className="text-xs text-status-danger">
            {uploadError}
          </p>
        )}
      </section>
    </div>
  );
}
