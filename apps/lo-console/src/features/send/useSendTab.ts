"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { fetchScenarios, type ScenariosView } from "../quote-builder/api";
import { useWorkspace } from "../workspace";
import {
  fetchLetterHtml,
  fetchPackage,
  fetchReadiness,
  fetchReport,
  savePackage,
  type Loaded,
  type PackageUpdate,
  type Readiness,
  type ReportViewModel,
  type SendPackage,
} from "./api";
import { editedPackageFields } from "./draft";

export type SendLoad =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; pkg: SendPackage; scenarios: ScenariosView };

export interface Previews {
  readiness: Loaded<Readiness> | null;
  report: Loaded<ReportViewModel> | null;
  letter: Loaded<string> | null;
}

const EMPTY_PREVIEWS: Previews = { readiness: null, report: null, letter: null };
const NO_QUOTES: Loaded<never> = { ok: false, message: "Select a quote to preview." };

export interface UseSendTabResult {
  applicationId: string;
  load: SendLoad;
  previews: Previews;
  saving: boolean;
  saveError: string | null;
  /** Persists the draft (optimistic); the server re-drafts the
   * recommendation text and the previews reload. */
  update: (draft: PackageUpdate) => Promise<void>;
  /** Re-sends the edits a failed save left unsaved. */
  retrySave: () => Promise<void>;
  /** Re-reads the package from the server (after a send: `sent_at`). */
  reload: () => Promise<void>;
  /** Bumps each time a save is refused with 409 `SEND_IN_PROGRESS`. */
  sendInProgressSignal: number;
}

export const SEND_IN_PROGRESS_MESSAGE =
  "This package is being sent, so your change wasn't saved. Edit again once the send finishes.";

export function useSendTab(): UseSendTabResult {
  const { applicationId, refetch: refetchWorkspace } = useWorkspace();
  const [load, setLoad] = useState<SendLoad>({ kind: "loading" });
  const [previews, setPreviews] = useState<Previews>(EMPTY_PREVIEWS);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  /** Edits whose save failed and that no later save has landed yet. Every
   * later save carries them, so a failed edit is never silently dropped by
   * a later successful save (PR #22 minor, CQ-020 T13): they stay on
   * screen and in the error until a save that includes them succeeds. */
  const unsavedEdits = useRef<Partial<PackageUpdate>>({});
  /** Bumped when a save is refused with SEND_IN_PROGRESS; the send flow
   * re-reads `send-status` on each bump and follows the running send. */
  const [sendInProgressSignal, setSendInProgressSignal] = useState(0);
  /** The last package the server actually confirmed (a save's response, or
   * the initial load) -- every queued save's body starts here, not from
   * whatever optimistic state happens to be on screen (M1, post-merge
   * review). */
  const latestConfirmed = useRef<SendPackage | null>(null);
  /** Chains saves so the next PUT only fires once the previous one's
   * response has landed (M1): two edits fired close together (e.g. a note
   * blur and a checkbox click) must not both build a full-draft PUT from
   * the same stale snapshot and race each other -- the second would win
   * and silently undo the first. */
  const saveQueue = useRef<Promise<void>>(Promise.resolve());
  const pendingSaves = useRef(0);
  /** Kept at the latest committed `applicationId` (a layout effect, so it
   * is current before any other effect or late response runs) so a queued
   * task started for a since-abandoned application can tell it's stale
   * once it resolves -- this hook doesn't remount on an `applicationId`
   * change (no `key` up the tree), so its refs would otherwise outlive the
   * navigation and a late response could write one application's data
   * into another's (code-review follow-up, post-merge review). */
  const applicationIdRef = useRef(applicationId);
  useLayoutEffect(() => {
    applicationIdRef.current = applicationId;
  }, [applicationId]);

  useEffect(() => {
    let active = true;
    // A fresh application: any save still in the queue was for the one
    // just left (guarded by `applicationIdRef` above regardless) and
    // shouldn't hold this one up.
    saveQueue.current = Promise.resolve();
    pendingSaves.current = 0;
    unsavedEdits.current = {};
    setSaving(false);
    setSaveError(null);
    Promise.all([fetchPackage(applicationId), fetchScenarios(applicationId)]).then(
      ([pkg, scenarios]) => {
        if (!active) return;
        if (!pkg.ok) {
          setLoad({ kind: "error", message: pkg.message });
        } else if (!scenarios.ok) {
          setLoad({ kind: "error", message: scenarios.problem.message });
        } else {
          latestConfirmed.current = pkg.data;
          setLoad({ kind: "ready", pkg: pkg.data, scenarios: scenarios.data });
        }
      },
    );
    return () => {
      active = false;
    };
  }, [applicationId]);

  const pkg = load.kind === "ready" ? load.pkg : null;
  const packageId = pkg?.id ?? null;
  const version = pkg?.updated_at ?? null;
  const hasQuotes = (pkg?.quote_ids.length ?? 0) > 0;

  useEffect(() => {
    if (packageId === null) return;
    let active = true;
    Promise.all([
      fetchReadiness(packageId),
      hasQuotes ? fetchReport(packageId) : Promise.resolve(NO_QUOTES),
      hasQuotes ? fetchLetterHtml(packageId) : Promise.resolve(NO_QUOTES),
    ]).then(([readiness, report, letter]) => {
      if (active) setPreviews({ readiness, report, letter });
    });
    return () => {
      active = false;
    };
  }, [packageId, version, hasQuotes]);

  const reload = useCallback(async () => {
    const forApplicationId = applicationId;
    const result = await fetchPackage(forApplicationId);
    if (applicationIdRef.current !== forApplicationId || !result.ok) return;
    // A save still queued or in flight will land its own response; don't
    // overwrite its optimistic edit with an older read.
    if (pendingSaves.current > 0) return;
    // A SEND_IN_PROGRESS notice is over once the send is.
    if (Object.keys(unsavedEdits.current).length === 0) setSaveError(null);
    latestConfirmed.current = result.data;
    setLoad((current) => (current.kind === "ready" ? { ...current, pkg: result.data } : current));
  }, [applicationId]);

  /** Queues one PUT. `edit` is the caller's own change; any edits a
   * failed save left unsaved ride along with it. */
  const enqueueSave = useCallback(
    async (edit: Partial<PackageUpdate>, previous: SendPackage) => {
      const forApplicationId = applicationId;
      setSaveError(null);
      pendingSaves.current += 1;
      setSaving(true);

      const runSave = async () => {
        try {
          // The application can have changed while this save waited its
          // turn in the queue (no remount on navigation) -- a queued task
          // for an abandoned application must not touch state at all.
          if (applicationIdRef.current !== forApplicationId) return;
          // Built from the latest *confirmed* state, not `previous` (which
          // can already be stale by the time this save's turn comes up),
          // so a field this call isn't touching still carries whatever the
          // previous queued save just landed (M1).
          const base = latestConfirmed.current ?? previous;
          // Read at run time (the queue is serial): an earlier save that
          // failed just before this one's turn is carried too (T13).
          const combined: Partial<PackageUpdate> = { ...unsavedEdits.current, ...edit };
          const body: PackageUpdate = {
            quote_ids: base.quote_ids,
            recommended_quote_id: base.recommended_quote_id ?? null,
            lo_note: base.lo_note ?? null,
            ...combined,
          };
          const result = await savePackage(forApplicationId, body);
          if (applicationIdRef.current !== forApplicationId) return;
          if (!result.ok) {
            if (result.code === "SEND_IN_PROGRESS") {
              // Nothing can be saved until the send finishes: drop the
              // optimistic edits, show the server's package again and let
              // the Send tab follow the running send.
              unsavedEdits.current = {};
              setSaveError(SEND_IN_PROGRESS_MESSAGE);
              const fresh = await fetchPackage(forApplicationId);
              if (applicationIdRef.current !== forApplicationId) return;
              if (fresh.ok) {
                latestConfirmed.current = fresh.data;
                setLoad((current) =>
                  current.kind === "ready" ? { ...current, pkg: fresh.data } : current,
                );
              }
              setSendInProgressSignal((n) => n + 1);
              return;
            }
            // Left on screen as-is (not reverted): reverting the whole
            // `pkg` to `latestConfirmed` would also wipe out any other
            // edit still queued behind this one and not yet sent. The edit
            // is kept for the next save (T13) and the error stays until a
            // save that includes it succeeds.
            unsavedEdits.current = combined;
            setSaveError(result.message);
            return;
          }
          // This save carried every unsaved edit, so a success here means
          // nothing is left unsaved.
          unsavedEdits.current = {};
          setSaveError(null);
          latestConfirmed.current = result.data;
          setLoad((current) =>
            current.kind === "ready" ? { ...current, pkg: result.data } : current,
          );
          // The header's note rate follows the recommended quote (CQ-016);
          // a PUT on a sent package reopens it (M3), so the status can move.
          if (
            result.data.recommended_quote_id !== base.recommended_quote_id ||
            result.data.sent_at !== base.sent_at
          ) {
            void refetchWorkspace();
          }
        } finally {
          // Guarded too: the fresh application's own load effect already
          // reset `pendingSaves` to 0 for it, so this stale task must not
          // decrement that counter out from under it.
          if (applicationIdRef.current === forApplicationId) {
            pendingSaves.current -= 1;
            if (pendingSaves.current === 0) setSaving(false);
          }
        }
      };

      // `runSave` as both handlers: an earlier task's rejection (it
      // shouldn't reject -- `savePackage` never throws -- but a `finally`
      // block does still propagate one) must not wedge every later save
      // behind a permanently-rejected queue.
      const task = saveQueue.current.then(runSave, runSave);
      saveQueue.current = task;
      await task;
    },
    [applicationId, refetchWorkspace],
  );

  const update = useCallback(
    async (draft: PackageUpdate) => {
      if (load.kind !== "ready") return;
      const previous = load.pkg;
      const edit = editedPackageFields(draft, previous);
      if (Object.keys(edit).length === 0) return;

      // Optimistic: layer just this edit onto whatever is on screen right
      // now (a functional update, so an edit still queued ahead of this
      // one isn't clobbered).
      setLoad((current) =>
        current.kind === "ready" ? { ...current, pkg: { ...current.pkg, ...edit } } : current,
      );
      await enqueueSave(edit, previous);
    },
    [load, enqueueSave],
  );

  const retrySave = useCallback(async () => {
    if (load.kind !== "ready" || Object.keys(unsavedEdits.current).length === 0) return;
    await enqueueSave({}, load.pkg);
  }, [load, enqueueSave]);

  return {
    applicationId,
    load,
    previews,
    saving,
    saveError,
    update,
    retrySave,
    reload,
    sendInProgressSignal,
  };
}
