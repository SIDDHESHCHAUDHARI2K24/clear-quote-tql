"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { extractErrorMessage } from "@cq/ui";

import { ActiveTabPane } from "./ActiveTabPane";
import type { ActiveTabPaneHandle } from "./ActiveTabPane";
import type { DraftPatchResponse, MetrosOut, SubmitResponse, Tab } from "./api";
import {
  TAB_ORDER,
  createOrGetDraft,
  getDraft,
  listMetros,
  parseAppError,
  patchDraft,
  submitDraft,
} from "./api";
import { Confirmation } from "./Confirmation";
import { getString } from "./paths";
import type { JsonRecord } from "./paths";
import { Stepper } from "./Stepper";

type LoadState = { kind: "loading" } | { kind: "error" } | { kind: "ready" };

const EMPTY_METROS: MetrosOut = { states: [] };

/**
 * `/apply` (spec.md): the four-tab wizard shell. Owns loading/creating the
 * borrower's draft (`POST /portal/applications`, which returns the open
 * one when there already is one -- AC3's resume), the metros list, the
 * stepper's active/unlocked tab, and the post-submit confirmation.
 *
 * Each tab's own form state and 1 s autosave live in `ActiveTabPane`
 * (remounted fresh via `key={activeTab}` on every tab switch); this
 * component only keeps the last *saved* snapshot of every tab
 * (`savedData`, refreshed from each save's response) so a tab that isn't
 * currently active can still supply cross-tab context -- tab 1's name for
 * tab 4's signature check, tab 2's occupancy for tab 3's income hint.
 */
export function ApplyWizard() {
  const [loadState, setLoadState] = useState<LoadState>({ kind: "loading" });
  const [draftId, setDraftId] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("you");
  const [unlockedTab, setUnlockedTab] = useState<Tab>("you");
  const [savedData, setSavedData] = useState<JsonRecord>({});
  const [consentVersion, setConsentVersion] = useState("");
  const [consentText, setConsentText] = useState("");
  const [metros, setMetros] = useState<MetrosOut>(EMPTY_METROS);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<SubmitResponse | null>(null);

  // Imperative handle onto the active `ActiveTabPane`'s own `saveNow`
  // (CQ-032b review round 1: Back and the Stepper used to switch tabs
  // without flushing a still-pending < 1 s autosave, so a quick "type then
  // click Back/Stepper" silently lost the edit -- the save timer got
  // cleared out from under it by `ActiveTabPane`'s `key={activeTab}`
  // remount before it ever fired). `onBack`/`goToTab` await it before
  // changing `activeTab`, the same way "Next" already flushes locally via
  // `handlePrimaryAction`. A failed flush (network error; `saveNow`
  // resolves `null`) keeps `activeTab` where it is -- the still-mounted
  // pane's own `saveStatus` shows the error.
  const paneRef = useRef<ActiveTabPaneHandle>(null);

  // Disables Back and the Stepper for the duration of `flushActiveTab`
  // (CQ-032b review round 1, code review: `runSave` is now re-entrant-safe
  // against a double-click firing two concurrent saves, but Back/Stepper
  // still looked clickable the whole time a flush was in flight -- this
  // keeps them visibly disabled too, and blocks Next/Submit for the same
  // window via the `switching` prop below).
  const [switchingTab, setSwitchingTab] = useState(false);

  const load = useCallback(async () => {
    setLoadState({ kind: "loading" });
    const [draftResult, metrosResult] = await Promise.all([createOrGetDraft(), listMetros()]);
    if (!draftResult.data) {
      setLoadState({ kind: "error" });
      return;
    }
    const draft = draftResult.data;
    setDraftId(draft.id);
    setEmail(draft.email);
    setActiveTab(draft.current_tab);
    setUnlockedTab(draft.current_tab);
    setSavedData(draft.data as JsonRecord);
    setConsentVersion(draft.consent.version);
    setConsentText(draft.consent.text);
    if (metrosResult.data) setMetros(metrosResult.data);
    setLoadState({ kind: "ready" });
  }, []);

  useEffect(() => {
    void load();
    // Mount-only (same reasoning as `HomeView`/`BorrowerSessionProvider`):
    // `load` never changes identity in a way that should re-trigger this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const patchTab = useCallback(
    async (tab: Tab, data: JsonRecord): Promise<DraftPatchResponse> => {
      if (!draftId) throw new Error("No draft yet");
      const { data: response, error } = await patchDraft(draftId, tab, data);
      if (!response) throw new Error(extractErrorMessage(error, "Could not save."));
      setSavedData(response.draft.data as JsonRecord);
      setUnlockedTab(response.draft.current_tab);
      return response;
    },
    [draftId],
  );

  /** Awaits the active pane's own `saveNow` (if a pane is mounted) and
   * reports whether it's safe to switch tabs now. `null` back from
   * `saveNow` means the PATCH failed -- don't switch. */
  async function flushActiveTab(): Promise<boolean> {
    if (!paneRef.current) return true;
    const response = await paneRef.current.saveNow();
    return response !== null;
  }

  async function goToTab(tab: Tab) {
    if (switchingTab || tab === activeTab) return;
    if (TAB_ORDER.indexOf(tab) > TAB_ORDER.indexOf(unlockedTab)) return;
    setSwitchingTab(true);
    try {
      if (!(await flushActiveTab())) return;
      setActiveTab(tab);
    } finally {
      setSwitchingTab(false);
    }
  }

  function onAdvance() {
    const next = TAB_ORDER[TAB_ORDER.indexOf(activeTab) + 1];
    if (next) setActiveTab(next);
  }

  async function onBack() {
    if (switchingTab) return;
    const prev = TAB_ORDER[TAB_ORDER.indexOf(activeTab) - 1];
    if (!prev) return;
    setSwitchingTab(true);
    try {
      if (!(await flushActiveTab())) return;
      setActiveTab(prev);
    } finally {
      setSwitchingTab(false);
    }
  }

  async function handleSubmit() {
    if (!draftId) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const { data: response, error } = await submitDraft(draftId);
      if (response) {
        setResult(response);
        return;
      }
      const appError = parseAppError(error);
      if (appError?.fieldErrors) {
        // Refresh from the server: a submit-time failure (e.g. a stored
        // SSN that no longer decrypts) may have changed what's saved.
        const { data: fresh } = await getDraft(draftId);
        if (fresh) {
          setSavedData(fresh.data as JsonRecord);
          setUnlockedTab(fresh.current_tab);
          setActiveTab(fresh.current_tab);
        } else {
          setActiveTab(appError.firstInvalidTab ?? "you");
        }
        setSubmitError(appError.message ?? "Some steps still need attention.");
        return;
      }
      setSubmitError(appError?.message ?? "Could not submit your application. Try again.");
    } catch {
      setSubmitError("Could not submit your application. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadState.kind === "loading") {
    return (
      <main role="status" aria-live="polite" className="flex flex-col gap-4">
        <p className="text-sm text-neutral-600">Loading your application…</p>
        <div className="h-24 animate-pulse rounded-lg bg-neutral-100" aria-hidden="true" />
      </main>
    );
  }

  if (loadState.kind === "error" || !draftId) {
    return (
      <main className="flex flex-col items-center gap-3 p-8 text-center">
        <h1 className="text-xl font-semibold text-navy-900">Something went wrong</h1>
        <p className="text-neutral-600">Try reloading the page.</p>
      </main>
    );
  }

  if (result) {
    return <Confirmation result={result} />;
  }

  const you = (savedData.you ?? {}) as JsonRecord;
  const youFullName = `${getString(you, "first_name")} ${getString(you, "last_name")}`.trim();
  const property = (savedData.property ?? {}) as JsonRecord;
  const propertyOccupancy = getString(property, "occupancy");

  return (
    <main className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-navy-900">Apply</h1>
      <Stepper
        activeTab={activeTab}
        unlockedTab={unlockedTab}
        onSelect={goToTab}
        disabled={switchingTab}
      />
      <ActiveTabPane
        key={activeTab}
        tab={activeTab}
        initialData={(savedData[activeTab] ?? {}) as JsonRecord}
        patchTab={patchTab}
        draftId={draftId}
        email={email}
        metros={metros}
        switching={switchingTab}
        youFullName={youFullName}
        propertyOccupancy={propertyOccupancy}
        consentVersion={consentVersion}
        consentText={consentText}
        onBack={onBack}
        onAdvance={onAdvance}
        onSubmit={handleSubmit}
        submitting={submitting}
        submitError={submitError}
        ref={paneRef}
      />
    </main>
  );
}
