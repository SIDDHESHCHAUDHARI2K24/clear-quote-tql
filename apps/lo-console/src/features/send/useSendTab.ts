"use client";

import { useCallback, useEffect, useRef, useState } from "react";

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
}

export function useSendTab(): UseSendTabResult {
  const { applicationId, refetch: refetchWorkspace } = useWorkspace();
  const [load, setLoad] = useState<SendLoad>({ kind: "loading" });
  const [previews, setPreviews] = useState<Previews>(EMPTY_PREVIEWS);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
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

  useEffect(() => {
    let active = true;
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
      setSaveError(null);
      pendingSaves.current += 1;
      setSaving(true);

      const task = saveQueue.current.then(async () => {
        // Built from the latest *confirmed* state, not `previous` (which
        // can already be stale by the time this save's turn comes up), so
        // a field this call isn't touching still carries whatever the
        // previous queued save just landed (M1).
        const base = latestConfirmed.current ?? previous;
        const body: PackageUpdate = {
          quote_ids: base.quote_ids,
          recommended_quote_id: base.recommended_quote_id ?? null,
          lo_note: base.lo_note ?? null,
          ...edit,
        };
        const result = await savePackage(applicationId, body);
        pendingSaves.current -= 1;
        if (pendingSaves.current === 0) setSaving(false);
        if (!result.ok) {
          setSaveError(result.message);
          const confirmed = latestConfirmed.current;
          if (confirmed) {
            setLoad((current) =>
              current.kind === "ready" ? { ...current, pkg: confirmed } : current,
            );
          }
          return;
        }
        latestConfirmed.current = result.data;
        setLoad((current) =>
          current.kind === "ready" ? { ...current, pkg: result.data } : current,
        );
        // The header's note rate follows the recommended quote (CQ-016).
        if (result.data.recommended_quote_id !== base.recommended_quote_id) {
          void refetchWorkspace();
        }
      });
      saveQueue.current = task;
      await task;
    },
    [applicationId, load, refetchWorkspace],
  );

  return { applicationId, load, previews, saving, saveError, update };
}
