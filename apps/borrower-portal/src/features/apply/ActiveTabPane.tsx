"use client";

import { useImperativeHandle, useState } from "react";
import type { Ref } from "react";

import { Button } from "@cq/ui";

import type { DraftPatchResponse, MetrosOut, Tab } from "./api";
import { TAB_ORDER } from "./api";
import { getString } from "./paths";
import type { JsonRecord } from "./paths";
import { ConsentTab } from "./tabs/ConsentTab";
import { IncomeTab } from "./tabs/IncomeTab";
import { PropertyTab } from "./tabs/PropertyTab";
import { YouTab } from "./tabs/YouTab";
import { useTabAutosave } from "./useTabAutosave";

export interface ActiveTabPaneProps {
  tab: Tab;
  initialData: JsonRecord;
  patchTab: (tab: Tab, data: JsonRecord) => Promise<DraftPatchResponse>;
  draftId: string;
  email: string;
  metros: MetrosOut;
  /** Tab 1's saved name, for tab 4's typed-signature check -- read from
   * `savedData.you`, not this pane's own `data` (which is only tab 1's
   * data when `tab === "you"`). */
  youFullName: string;
  propertyOccupancy: string;
  consentVersion: string;
  consentText: string;
  onBack: () => void;
  onAdvance: () => void;
  onSubmit: () => Promise<void>;
  submitting: boolean;
  submitError: string | null;
  /** True while `ApplyWizard` is mid-flush of this pane's pending autosave
   * from a Back or Stepper click (CQ-032b review round 1): disables Back
   * and Next/Submit for that window too, on top of `actionInFlight`
   * below (which covers Next/Submit's own round trip) -- `saveNow` itself
   * is also re-entrant-safe, so this is belt-and-suspenders UI feedback,
   * not the only thing preventing a double PATCH. */
  switching?: boolean;
  ref?: Ref<ActiveTabPaneHandle>;
}

/** Exposes this pane's own `saveNow` to `ApplyWizard` via `ref` (React 19
 * ref-as-prop + `useImperativeHandle` -- no `forwardRef` needed) so
 * `onBack` and the Stepper's `goToTab` can await a flush of whatever's
 * still mid-debounce before switching tabs, the same flush "Next" already
 * does locally via `handlePrimaryAction` (CQ-032b review round 1:
 * switching tabs used to drop a pending < 1 s edit silently). `key={tab}`
 * on the caller's side means React nulls out the ref on unmount and sets
 * it fresh on the next pane's mount, so `ApplyWizard`'s ref always points
 * at the currently-active pane, never a stale one. */
export interface ActiveTabPaneHandle {
  saveNow: () => Promise<DraftPatchResponse | null>;
}

function renderTabBody(
  tab: Tab,
  common: {
    data: JsonRecord;
    set: ReturnType<typeof useTabAutosave>["set"];
    errorFor: ReturnType<typeof useTabAutosave>["errorFor"];
    disabled: boolean;
  },
  extra: Pick<
    ActiveTabPaneProps,
    | "email"
    | "metros"
    | "draftId"
    | "propertyOccupancy"
    | "youFullName"
    | "consentVersion"
    | "consentText"
  >,
) {
  switch (tab) {
    case "you":
      return <YouTab {...common} email={extra.email} />;
    case "property":
      return <PropertyTab {...common} metros={extra.metros} />;
    case "income":
      return <IncomeTab {...common} draftId={extra.draftId} occupancy={extra.propertyOccupancy} />;
    case "consent":
      return (
        <ConsentTab
          {...common}
          expectedName={extra.youFullName}
          consentVersion={extra.consentVersion}
          consentText={extra.consentText}
        />
      );
    default:
      return null;
  }
}

/** One tab's form plus its own autosave (via `useTabAutosave`, reset
 * fresh whenever `ApplyWizard` remounts this pane with `key={tab}`) and
 * the shared Back/Next-or-Submit button bar. Co-locating the hook and the
 * buttons means "Next" can call this tab's own `saveNow()` directly. */
export function ActiveTabPane({
  tab,
  initialData,
  patchTab,
  draftId,
  email,
  metros,
  youFullName,
  propertyOccupancy,
  consentVersion,
  consentText,
  onBack,
  onAdvance,
  onSubmit,
  submitting,
  submitError,
  switching = false,
  ref,
}: ActiveTabPaneProps) {
  const { data, set, errorFor, saveStatus, saveNow } = useTabAutosave(tab, initialData, patchTab);
  const index = TAB_ORDER.indexOf(tab);
  const isLast = tab === "consent";
  // Guards Next/Submit against a double-click firing two saves/submits at
  // once (CQ-032b review round 1, minor): true for the whole
  // save-then-advance-or-submit round trip, not just the save.
  const [actionInFlight, setActionInFlight] = useState(false);
  const disabled = (isLast && submitting) || actionInFlight || switching;

  useImperativeHandle(ref, () => ({ saveNow }), [saveNow]);

  // Tab 4's typed-name check compares against tab 1's *saved* name; while
  // tab 1 is the active tab, that's this pane's own (still-saving) data.
  const effectiveYouFullName =
    tab === "you"
      ? `${getString(data, "first_name")} ${getString(data, "last_name")}`.trim()
      : youFullName;

  async function handlePrimaryAction() {
    if (actionInFlight) return;
    setActionInFlight(true);
    try {
      const response = await saveNow();
      if (!response || !response.tab_valid) return;
      if (isLast) {
        await onSubmit();
      } else {
        onAdvance();
      }
    } finally {
      setActionInFlight(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {renderTabBody(
        tab,
        { data, set, errorFor, disabled },
        {
          email,
          metros,
          draftId,
          propertyOccupancy,
          youFullName: effectiveYouFullName,
          consentVersion,
          consentText,
        },
      )}

      <div className="flex flex-col gap-2 border-t border-neutral-100 pt-4">
        <div aria-live="polite">
          {saveStatus === "pending" && <p className="text-xs text-neutral-500">Saving…</p>}
          {saveStatus === "saved" && <p className="text-xs text-status-success">Saved</p>}
          {saveStatus === "error" && (
            <p role="alert" className="text-xs text-status-danger">
              Couldn&rsquo;t save. Check your connection and try again.
            </p>
          )}
        </div>
        {isLast && submitError && (
          <p role="alert" className="text-sm text-status-danger">
            {submitError}
          </p>
        )}
        <div className="flex gap-3">
          {index > 0 && (
            <Button
              type="button"
              variant="secondary"
              disabled={disabled}
              onClick={() => void onBack()}
            >
              Back
            </Button>
          )}
          <Button
            type="button"
            disabled={disabled}
            isLoading={(isLast && submitting) || actionInFlight}
            onClick={() => void handlePrimaryAction()}
          >
            {isLast ? "Submit application" : "Next"}
          </Button>
        </div>
      </div>
    </div>
  );
}
