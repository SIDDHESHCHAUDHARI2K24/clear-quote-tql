"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import {
  fetchSendStatus,
  fetchSentVersions,
  startSend,
  type Loaded,
  type ReadinessBlocker,
  type SendStep,
  type SentVersion,
} from "./api";

/** How often the progress is polled while a send runs (handoff 1: ~500 ms). */
export const SEND_POLL_MS = 500;
/** Consecutive failed status reads before the tab gives up (about 5 s). */
export const SEND_POLL_MAX_FAILURES = 10;

export type RunningStep = Extract<SendStep, "queued" | "rendering" | "emailing">;

export type SendPhase =
  | { kind: "idle" }
  | { kind: "starting" }
  | { kind: "running"; step: RunningStep; tick: number }
  | { kind: "done"; recipient: string | null }
  | { kind: "failed"; message: string }
  | { kind: "blocked"; message: string; blockers: ReadinessBlocker[] };

const RUNNING_STEPS: readonly SendStep[] = ["queued", "rendering", "emailing"];

export function isRunningStep(step: SendStep): step is RunningStep {
  return RUNNING_STEPS.includes(step);
}

export interface UseSendFlowOptions {
  /** Called once a send reaches `done` (refetch the workspace summary and
   * the package so the status pill and `sent_at` follow). */
  onSent: () => void;
  /** Each change re-reads `GET /send-status` (bumped when a `PUT` was
   * refused with `SEND_IN_PROGRESS`, so a send started elsewhere is
   * picked up). */
  resyncKey?: number;
}

export interface UseSendFlowResult {
  phase: SendPhase;
  /** A send is starting or running: the Send tab locks its edits. */
  inFlight: boolean;
  versions: Loaded<SentVersion[]> | null;
  toast: string | null;
  dismissToast: () => void;
  /** `POST /send`, then poll `GET /send-status` until done or failed. */
  start: () => Promise<void>;
  /** Back to idle (closing the dialog after a finished, failed or blocked
   * send). A running send keeps running. */
  reset: () => void;
}

/** The send workflow as seen from the Send tab (CQ-020 T10–T12). Progress
 * comes from the DB-backed `send-status` (plan.md Decision 7), so a reload
 * mid-send resumes polling where it left off. */
export function useSendFlow(
  packageId: string | null,
  { onSent, resyncKey = 0 }: UseSendFlowOptions,
): UseSendFlowResult {
  const [phase, setPhase] = useState<SendPhase>({ kind: "idle" });
  const [versions, setVersions] = useState<Loaded<SentVersion[]> | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  /** Guards late responses after the tab moved to another package. */
  const packageIdRef = useRef(packageId);
  useLayoutEffect(() => {
    packageIdRef.current = packageId;
  }, [packageId]);
  /** Consecutive failed `send-status` reads while polling. */
  const failedPolls = useRef(0);

  const loadVersions = useCallback(async (forPackageId: string) => {
    const result = await fetchSentVersions(forPackageId);
    if (packageIdRef.current === forPackageId) setVersions(result);
  }, []);

  // On open (and on `resync`): pick up a send already in flight, and the
  // version history.
  useEffect(() => {
    if (packageId === null) return;
    let active = true;
    setVersions(null);
    fetchSendStatus(packageId).then((status) => {
      if (!active || !status.ok) return;
      const step = status.data.status;
      if (isRunningStep(step)) {
        failedPolls.current = 0;
        setPhase({ kind: "running", step, tick: 0 });
      } else if (step === "failed") {
        setPhase({ kind: "failed", message: status.data.error ?? "The last send failed." });
      } else if (step === "done" && resyncKey > 0) {
        // A resync after a SEND_IN_PROGRESS refusal whose send finished in
        // between: the pill, `sent_at` and the save notice must follow.
        onSent();
      }
    });
    void loadVersions(packageId);
    return () => {
      active = false;
    };
  }, [packageId, resyncKey, loadVersions, onSent]);

  // Polls while running: each result sets a fresh `running` phase (new
  // `tick`), which schedules the next poll.
  useEffect(() => {
    if (phase.kind !== "running" || packageId === null) return;
    const forPackageId = packageId;
    let active = true;
    const timer = setTimeout(async () => {
      const status = await fetchSendStatus(forPackageId);
      if (!active || packageIdRef.current !== forPackageId) return;
      if (!status.ok) {
        // A blip while polling: keep polling, the workflow keeps running.
        // A status read that keeps failing (session expired, API down)
        // stops after a few seconds instead of locking the tab forever.
        failedPolls.current += 1;
        if (failedPolls.current >= SEND_POLL_MAX_FAILURES) {
          setPhase({
            kind: "failed",
            message: `Couldn't check the send's progress (${status.message}). Reload to see where it stands.`,
          });
          return;
        }
        setPhase({ kind: "running", step: phase.step, tick: phase.tick + 1 });
        return;
      }
      failedPolls.current = 0;
      const { status: step, error, recipient_email: recipient } = status.data;
      if (isRunningStep(step)) {
        setPhase({ kind: "running", step, tick: phase.tick + 1 });
      } else if (step === "done") {
        setPhase({ kind: "done", recipient });
        setToast(recipient ? `Sent to ${recipient}` : "Sent");
        onSent();
        void loadVersions(forPackageId);
      } else if (step === "failed") {
        setPhase({ kind: "failed", message: error ?? "The send failed. Try again." });
      } else {
        setPhase({ kind: "idle" });
      }
    }, SEND_POLL_MS);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [phase, packageId, loadVersions, onSent]);

  const start = useCallback(async () => {
    if (packageId === null) return;
    const forPackageId = packageId;
    setPhase({ kind: "starting" });
    const result = await startSend(forPackageId);
    if (packageIdRef.current !== forPackageId) return;
    if (!result.ok) {
      if (result.code === "PACKAGE_NOT_READY") {
        setPhase({ kind: "blocked", message: result.message, blockers: result.blockers ?? [] });
      } else {
        setPhase({ kind: "failed", message: result.message });
      }
      return;
    }
    // A double click returns the running send's id; either way, poll.
    const step = result.data.status;
    failedPolls.current = 0;
    setPhase({ kind: "running", step: isRunningStep(step) ? step : "queued", tick: 0 });
  }, [packageId]);

  const reset = useCallback(() => {
    setPhase((current) =>
      current.kind === "running" || current.kind === "starting" ? current : { kind: "idle" },
    );
  }, []);

  const dismissToast = useCallback(() => setToast(null), []);

  // The toast hides itself after a few seconds.
  useEffect(() => {
    if (toast === null) return;
    const timer = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(timer);
  }, [toast]);

  const inFlight = phase.kind === "starting" || phase.kind === "running";
  return { phase, inFlight, versions, toast, dismissToast, start, reset };
}
