"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { DraftPatchResponse, Tab } from "./api";
import { setPath } from "./paths";
import type { JsonRecord } from "./paths";

export type SaveStatus = "idle" | "pending" | "saved" | "error";

const AUTOSAVE_DELAY_MS = 1000;

export interface UseTabAutosave {
  data: JsonRecord;
  /** Applies an immutable update to the tab's data and (re)starts the 1 s
   * autosave timer. `touchedPath`, when given, marks that dotted path so
   * its error shows immediately rather than only after "Next" (spec.md's
   * "the UI shows errors only for touched fields (or all of them on
   * Next)"). */
  set: (path: string, value: unknown, touchedPath?: string) => void;
  fieldErrors: Record<string, string>;
  errorFor: (path: string) => string | undefined;
  saveStatus: SaveStatus;
  /** Cancels any pending debounce and saves immediately, revealing every
   * field's error (for "Next"/"Submit"). Resolves with the server's
   * validation result, or `null` on a network failure. */
  saveNow: () => Promise<DraftPatchResponse | null>;
}

/** Owns one tab's autosave: local edits merge into `data`, a 1 s idle
 * timer PATCHes the whole tab (plan.md decision 3: "the UI always sends
 * the full tab"), and the response's `field_errors` drive validation
 * display. One instance per active tab, created fresh (new `initialData`)
 * whenever the wizard switches tabs -- see `ApplyWizard`'s `key={tab}`. */
export function useTabAutosave(
  tab: Tab,
  initialData: JsonRecord,
  patchTab: (tab: Tab, data: JsonRecord) => Promise<DraftPatchResponse>,
): UseTabAutosave {
  const [data, setData] = useState<JsonRecord>(initialData);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [showAll, setShowAll] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");

  // Kept in sync via an effect (not a direct render-time assignment,
  // which react-doctor's `no-ref-current-in-render` flags -- concurrent
  // rendering can call the render body more than once per commit) so
  // `runSave`'s callback -- always invoked well after commit, either from
  // a debounce timer or a click handler -- reads the latest value without
  // needing `data` in its own dependency list.
  const dataRef = useRef(data);
  useEffect(() => {
    dataRef.current = data;
  }, [data]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runSave = useCallback(async (): Promise<DraftPatchResponse | null> => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setSaveStatus("pending");
    try {
      const response = await patchTab(tab, dataRef.current);
      setFieldErrors(response.field_errors);
      setSaveStatus("saved");
      return response;
    } catch {
      setSaveStatus("error");
      return null;
    }
  }, [patchTab, tab]);

  const set = useCallback(
    (path: string, value: unknown, touchedPath?: string) => {
      setData((prev) => setPath(prev, path, value));
      const mark = touchedPath ?? path;
      setTouched((prev) => (prev.has(mark) ? prev : new Set(prev).add(mark)));
      setSaveStatus("idle");
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        void runSave();
      }, AUTOSAVE_DELAY_MS);
    },
    [runSave],
  );

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const saveNow = useCallback(async () => {
    setShowAll(true);
    return runSave();
  }, [runSave]);

  const errorFor = useCallback(
    (path: string) => (showAll || touched.has(path) ? fieldErrors[path] : undefined),
    [showAll, touched, fieldErrors],
  );

  return { data, set, fieldErrors, errorFor, saveStatus, saveNow };
}
