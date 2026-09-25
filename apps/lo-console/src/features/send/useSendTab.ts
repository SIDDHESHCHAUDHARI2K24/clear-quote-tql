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
  const latestSave = useRef(0);

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
      const request = ++latestSave.current;
      setLoad({ ...load, pkg: { ...previous, ...draft } });
      setSaving(true);
      setSaveError(null);
      let result: Awaited<ReturnType<typeof savePackage>>;
      try {
        result = await savePackage(applicationId, draft);
      } finally {
        if (request === latestSave.current) setSaving(false);
      }
      if (request !== latestSave.current) return;
      if (!result.ok) {
        setSaveError(result.message);
        setLoad({ ...load, pkg: previous });
        return;
      }
      setLoad({ ...load, pkg: result.data });
      // The header's note rate follows the recommended quote (CQ-016).
      if (result.data.recommended_quote_id !== previous.recommended_quote_id) {
        void refetchWorkspace();
      }
    },
    [applicationId, load, refetchWorkspace],
  );

  return { applicationId, load, previews, saving, saveError, update };
}
