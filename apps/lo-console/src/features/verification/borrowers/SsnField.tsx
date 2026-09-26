"use client";

import { useEffect, useRef, useState } from "react";

import { SourceBadge, extractErrorMessage } from "@cq/ui";
import type { SourceBadgeSource } from "@cq/ui";

import { putField, revealSsn, revertField, runSectionAction } from "../shared";
import type { SectionField, SectionFlag, SectionResponse } from "../shared";

const REVEAL_DURATION_MS = 10000;

export interface SsnFieldProps {
  applicationId: string;
  /** The owning party's id (null defensively -- a party record should
   * always have one, but `SectionRecord.id` is typed nullable). Reveal is
   * disabled without it. */
  partyId: string | null;
  field: SectionField;
  flag?: SectionFlag;
  applyResult: (section: SectionResponse) => void;
}

function maskedDisplay(value: SectionField["value"]): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

// `revealSsn` returns the raw 9 digits, no dashes -- format for readability
// only (string slicing, not money math, per AGENTS.md).
function formatRawSsn(digits: string): string {
  return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5, 9)}`;
}

/** SSN display, reveal and edit-in-place for a party's SSN field.
 *
 * docs/backlog/CQ-028-verification-tabs/spec.md AC7: "revealing an SSN
 * writes an event and re-masks after 10 s". The backend already writes the
 * activity event inside `POST .../ssn-reveal` -- this component only owns
 * the 10s local re-mask timer (see `SsnField.test.tsx` for the AC7 test).
 */
export function SsnField({ applicationId, partyId, field, flag, applyResult }: SsnFieldProps) {
  const [revealed, setRevealed] = useState<string | null>(null);
  const [revealing, setRevealing] = useState(false);
  const [revealError, setRevealError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [prevFieldValue, setPrevFieldValue] = useState(field.value);

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  // Clear any pending re-mask timer on unmount.
  useEffect(() => clearTimer, []);

  // If the underlying field value changes (a refetch/edit/revert landed)
  // while revealed, drop back to the masked display immediately instead of
  // showing stale raw digits for the rest of the window -- adjusted during
  // render (React's documented "storing information from previous renders"
  // pattern, tracked in state rather than a ref so this stays safe under
  // concurrent rendering: react-doctor/no-ref-current-in-render) rather
  // than a `useEffect` keyed on `field.value`
  // (react-doctor/no-adjust-state-on-prop-change), which would show the
  // stale revealed value for one extra render before the effect ran. The
  // pending timer itself needs no explicit clear here: `reveal()` already
  // clears any existing timer before starting a new one, so a timer left
  // over from before this change either already fired (harmless -- it just
  // sets `revealed` to `null`, which it already is) or gets cleared by the
  // next `reveal()` call.
  if (field.value !== prevFieldValue) {
    setPrevFieldValue(field.value);
    if (revealed !== null) setRevealed(null);
  }

  const reveal = async () => {
    if (!partyId) return;
    setRevealing(true);
    setRevealError(null);
    try {
      const { data, error } = await revealSsn(applicationId, partyId);
      if (!data) {
        setRevealError(extractErrorMessage(error, "Could not reveal the SSN."));
        return;
      }
      setRevealed(data.ssn ? formatRawSsn(data.ssn) : "—");
      clearTimer();
      timerRef.current = setTimeout(() => {
        setRevealed(null);
        timerRef.current = null;
      }, REVEAL_DURATION_MS);
    } catch {
      setRevealError("Could not reveal the SSN.");
    } finally {
      setRevealing(false);
    }
  };

  const startEdit = () => {
    setDraft("");
    setSaveError(null);
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setSaveError(null);
  };

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const result = await runSectionAction(() =>
        putField(applicationId, field.field_key, draft.trim() === "" ? null : draft.trim()),
      );
      if (!result.ok) throw new Error(result.message);
      applyResult(result.section);
      setEditing(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  };

  const revert = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const result = await runSectionAction(() => revertField(applicationId, field.field_key));
      if (!result.ok) throw new Error(result.message);
      applyResult(result.section);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not revert.");
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
            onRevert={field.overridden ? () => void revert() : undefined}
          />
          {!editing && (
            <button
              type="button"
              onClick={() => void reveal()}
              disabled={revealing || !partyId}
              className="text-xs font-medium text-navy-600 underline hover:text-navy-900 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Reveal
            </button>
          )}
          {field.editable && !editing && (
            <button
              type="button"
              onClick={startEdit}
              disabled={saving}
              className="text-xs font-medium text-navy-600 underline hover:text-navy-900"
            >
              Edit
            </button>
          )}
        </div>
      </div>

      {editing ? (
        <div className="flex flex-wrap items-center gap-2">
          <input
            aria-label={field.label}
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="h-9 rounded-md border border-neutral-200 px-2 text-sm"
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
            onClick={cancelEdit}
            disabled={saving}
            className="text-xs font-medium text-neutral-600 underline"
          >
            Cancel
          </button>
        </div>
      ) : (
        <span className="text-sm text-navy-900">{revealed ?? maskedDisplay(field.value)}</span>
      )}

      {revealError && <p className="text-xs text-status-danger">{revealError}</p>}
      {saveError && <p className="text-xs text-status-danger">{saveError}</p>}
      {flagged && <p className="text-xs font-medium text-status-danger">{flag.message}</p>}
    </div>
  );
}
