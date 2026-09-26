"use client";

import { useCallback, useEffect, useState } from "react";

import { useWorkspace } from "../workspace";
import {
  deleteQuote,
  fetchScenarios,
  recommendQuote,
  repriceApplication,
  type PricingProblem,
  type Result,
  type ScenariosView,
} from "./api";

export type BuilderLoad =
  { kind: "loading" } | { kind: "error" } | { kind: "ready"; view: ScenariosView };

export interface UseQuoteBuilderResult {
  applicationId: string;
  load: BuilderLoad;
  /** A pending mutation: cards show a loading state while it runs. */
  busy: boolean;
  problem: PricingProblem | null;
  setProblem: (problem: PricingProblem | null) => void;
  reload: () => Promise<void>;
  /** `reload` plus the workspace header (note rate). */
  refresh: () => Promise<void>;
  /** Runs a mutation, then refreshes the cards and the workspace header
   * (the CQ-016 note rate follows the recommended quote). */
  run: <T>(action: () => Promise<Result<T>>) => Promise<Result<T>>;
  recommend: (quoteId: string) => Promise<void>;
  remove: (quoteId: string) => Promise<void>;
  reprice: () => Promise<void>;
}

export function useQuoteBuilder(): UseQuoteBuilderResult {
  const { applicationId, refetch: refetchWorkspace } = useWorkspace();
  const [load, setLoad] = useState<BuilderLoad>({ kind: "loading" });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<PricingProblem | null>(null);

  const reload = useCallback(async () => {
    const result = await fetchScenarios(applicationId);
    setLoad(result.ok ? { kind: "ready", view: result.data } : { kind: "error" });
  }, [applicationId]);

  useEffect(() => {
    let active = true;
    fetchScenarios(applicationId).then((result) => {
      if (!active) return;
      setLoad(result.ok ? { kind: "ready", view: result.data } : { kind: "error" });
    });
    return () => {
      active = false;
    };
  }, [applicationId]);

  const refresh = useCallback(async () => {
    await reload();
    await refetchWorkspace();
  }, [reload, refetchWorkspace]);

  const run = useCallback(
    async <T>(action: () => Promise<Result<T>>): Promise<Result<T>> => {
      setBusy(true);
      setProblem(null);
      try {
        const result = await action();
        if (!result.ok) setProblem(result.problem);
        await refresh();
        return result;
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const recommend = useCallback(
    async (quoteId: string) => {
      await run(() => recommendQuote(quoteId));
    },
    [run],
  );

  const remove = useCallback(
    async (quoteId: string) => {
      await run(() => deleteQuote(quoteId));
    },
    [run],
  );

  const reprice = useCallback(async () => {
    await run(() => repriceApplication(applicationId));
  }, [run, applicationId]);

  return {
    applicationId,
    load,
    busy,
    problem,
    setProblem,
    reload,
    refresh,
    run,
    recommend,
    remove,
    reprice,
  };
}
