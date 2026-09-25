"use client";

import { useState } from "react";

import { Button, Overlay, extractErrorMessage } from "@cq/ui";

import { patchApplicationStatus } from "./api";
import type { StatusPatchStatus } from "./api";
import { useWorkspace } from "./WorkspaceProvider";

const TERMINAL_STATUSES = new Set(["withdrawn", "closed"]);

const ACTION_LABEL: Record<StatusPatchStatus, string> = {
  withdrawn: "Withdraw application",
  closed: "Close application",
};

// spec.md "Header actions menu": "Withdraw application" and "Close
// application" (confirm dialog + reason field). Both hidden when the
// status is already terminal (AC6).
export function StatusActionsMenu() {
  const { applicationId, state, refetch } = useWorkspace();
  const [menuOpen, setMenuOpen] = useState(false);
  const [pendingAction, setPendingAction] = useState<StatusPatchStatus | null>(null);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (state.kind !== "ready" || TERMINAL_STATUSES.has(state.summary.status)) {
    return null;
  }

  function openConfirm(action: StatusPatchStatus) {
    setPendingAction(action);
    setReason("");
    setError(null);
    setMenuOpen(false);
  }

  function closeConfirm() {
    if (submitting) return;
    setPendingAction(null);
  }

  async function confirm() {
    if (!pendingAction) return;
    setSubmitting(true);
    setError(null);
    try {
      const { data, error: err } = await patchApplicationStatus(
        applicationId,
        pendingAction,
        reason,
      );
      if (!data) {
        setError(extractErrorMessage(err, "Something went wrong. Try again."));
        return;
      }
      setPendingAction(null);
      await refetch();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative">
      <Button
        variant="secondary"
        onClick={() => setMenuOpen((open) => !open)}
        rightIcon={<span aria-hidden="true">▾</span>}
      >
        Actions
      </Button>
      {menuOpen && (
        <div
          role="menu"
          className="absolute right-0 z-10 mt-1 w-56 rounded-md border border-neutral-200 bg-neutral-0 py-1 shadow-lg"
        >
          <button
            type="button"
            role="menuitem"
            className="block w-full px-3 py-2 text-left text-sm text-navy-900 hover:bg-neutral-50"
            onClick={() => openConfirm("withdrawn")}
          >
            Withdraw application
          </button>
          <button
            type="button"
            role="menuitem"
            className="block w-full px-3 py-2 text-left text-sm text-navy-900 hover:bg-neutral-50"
            onClick={() => openConfirm("closed")}
          >
            Close application
          </button>
        </div>
      )}
      <Overlay
        isOpen={pendingAction !== null}
        onClose={closeConfirm}
        title={pendingAction ? ACTION_LABEL[pendingAction] : ""}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={closeConfirm}>
              Cancel
            </Button>
            <Button variant="danger" isLoading={submitting} onClick={confirm}>
              Confirm
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-3">
          {error && (
            <p role="alert" className="text-sm text-status-danger">
              {error}
            </p>
          )}
          <label className="flex flex-col gap-1 text-sm text-navy-900">
            Reason (optional)
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={3}
              className="rounded-md border border-neutral-300 px-2 py-1 text-sm"
            />
          </label>
        </div>
      </Overlay>
    </div>
  );
}
