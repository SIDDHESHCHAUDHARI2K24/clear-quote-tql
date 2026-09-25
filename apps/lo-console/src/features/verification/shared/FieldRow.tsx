"use client";

import { useState } from "react";

import { SourceBadge } from "@cq/ui";
import type { SourceBadgeSource } from "@cq/ui";

import { formatFieldValue } from "./format";
import type { SectionField, SectionFlag } from "./api";

export type FieldRowKind = "text" | "number" | "date" | "boolean" | "select" | "money";

export interface FieldRowOption {
  value: string;
  label: string;
}

export interface FieldRowProps {
  field: SectionField;
  /** The tab's open flag for this exact `field_key`, if any (spec.md: "Each
   * flagged field is highlighted with its message inline"). */
  flag?: SectionFlag;
  kind?: FieldRowKind;
  options?: FieldRowOption[];
  /** Saves a new value (`PUT /fields/{key}` or a row/party PATCH, wrapped by
   * the caller). Resolving throws/rejects to keep editing open; the caller
   * is responsible for surfacing the error message. */
  onSave: (value: string | number | boolean | null) => Promise<void>;
  /** Omitted when the field cannot be reverted (not overridden, or a
   * caller-level reason, e.g. a manually-added row). */
  onRevert?: () => Promise<void>;
  disabled?: boolean;
}

function toInputValue(value: SectionField["value"]): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

// Throws on an invalid "number" draft instead of returning `NaN` --
// `JSON.stringify(NaN)` serializes to `null`, so an unvalidated `Number()`
// here would silently save a bad entry (e.g. "abc") as a field-clear
// instead of surfacing a validation error to the LO (code-review finding).
function draftToValue(kind: FieldRowKind, draft: string): string | number | boolean | null {
  if (kind === "boolean") return draft === "true";
  if (kind === "number") {
    if (draft.trim() === "") return null;
    const parsed = Number(draft);
    if (Number.isNaN(parsed)) throw new Error("Enter a number.");
    return parsed;
  }
  return draft.trim() === "" ? null : draft;
}

interface FieldRowEditorProps {
  label: string;
  kind: FieldRowKind;
  options?: FieldRowOption[];
  draft: string;
  onDraftChange: (value: string) => void;
}

// Pulled out of `FieldRow` so its own control flow (one branch per `kind`)
// doesn't count against the parent function's complexity
// (react-doctor/no-high-complexity-react-function) -- same markup as before.
function FieldRowEditor({ label, kind, options, draft, onDraftChange }: FieldRowEditorProps) {
  if (kind === "boolean") {
    return (
      <select
        aria-label={label}
        value={draft}
        onChange={(e) => onDraftChange(e.target.value)}
        className="h-9 rounded-md border border-neutral-200 px-2 text-sm"
      >
        <option value="false">No</option>
        <option value="true">Yes</option>
      </select>
    );
  }
  if (kind === "select") {
    return (
      <select
        aria-label={label}
        value={draft}
        onChange={(e) => onDraftChange(e.target.value)}
        className="h-9 rounded-md border border-neutral-200 px-2 text-sm"
      >
        <option value="">—</option>
        {(options ?? []).map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }
  return (
    <input
      aria-label={label}
      type={kind === "date" ? "date" : "text"}
      inputMode={kind === "number" || kind === "money" ? "decimal" : undefined}
      value={draft}
      onChange={(e) => onDraftChange(e.target.value)}
      className="h-9 rounded-md border border-neutral-200 px-2 text-sm"
    />
  );
}

/** One editable 1003 field: label, formatted value, `SourceBadge` (with the
 * built-in "revert" action once overridden), inline edit, and the matching
 * flag's message highlighted in red (spec.md "Shared pieces"). */
export function FieldRow({
  field,
  flag,
  kind = "text",
  options,
  onSave,
  onRevert,
  disabled = false,
}: FieldRowProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => toInputValue(field.value));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startEdit = () => {
    setDraft(toInputValue(field.value));
    setError(null);
    setEditing(true);
  };

  const cancel = () => {
    setEditing(false);
    setError(null);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await onSave(draftToValue(kind, draft));
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  };

  const revert = async () => {
    if (!onRevert) return;
    setSaving(true);
    setError(null);
    try {
      await onRevert();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not revert.");
    } finally {
      setSaving(false);
    }
  };

  const flagged = flag !== undefined;

  return (
    <div
      className={`flex flex-col gap-1 border-b border-neutral-100 py-2 last:border-0 ${
        flagged ? "rounded-md bg-status-danger/5 px-2" : ""
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium text-navy-900">{field.label}</span>
        <div className="flex items-center gap-2">
          <SourceBadge
            source={field.source as SourceBadgeSource}
            onRevert={onRevert ? () => void revert() : undefined}
          />
          {field.editable && !editing && (
            <button
              type="button"
              onClick={startEdit}
              disabled={disabled || saving}
              className="text-xs font-medium text-navy-600 underline hover:text-navy-900"
            >
              Edit
            </button>
          )}
        </div>
      </div>

      {editing ? (
        <div className="flex flex-wrap items-center gap-2">
          <FieldRowEditor
            label={field.label}
            kind={kind}
            options={options}
            draft={draft}
            onDraftChange={setDraft}
          />
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving}
            className="rounded-md bg-navy-700 px-3 py-1.5 text-xs font-medium text-neutral-0 disabled:opacity-50"
          >
            Save
          </button>
          <button
            type="button"
            onClick={cancel}
            disabled={saving}
            className="text-xs font-medium text-neutral-600 underline"
          >
            Cancel
          </button>
        </div>
      ) : (
        <span className="text-sm text-navy-900">{formatFieldValue(field, kind, options)}</span>
      )}

      {error && <p className="text-xs text-status-danger">{error}</p>}
      {flagged && <p className="text-xs font-medium text-status-danger">{flag.message}</p>}
    </div>
  );
}
