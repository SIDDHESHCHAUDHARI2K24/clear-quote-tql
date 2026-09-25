"use client";

import { useState } from "react";

import { Button, Overlay } from "@cq/ui";

const MAX_MESSAGE_LENGTH = 500;

export interface AskOtherDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (message: string) => void;
  optionLabel: string;
  submitting: boolean;
  error: string | null;
}

/** spec.md: dialog with a textarea (placeholder "What would you like to
 * change? For example, a lower cash to close.") and the current option
 * shown for context.
 *
 * Fresh-subagent review finding: a successful submit closes this dialog
 * from the *caller* (`ReportActionsSlot`'s `onSuccess`, which flips
 * `dialog.kind` to `"none"`), not through this component's own
 * `handleClose` -- an earlier fix that reset `message` in a `useEffect`
 * keyed on `isOpen` worked, but is the exact "adjust state on prop
 * change" anti-pattern (react.dev, also flagged by react-doctor's
 * `no-adjust-state-on-prop-change`/`no-reset-all-state-on-prop-change`).
 * The idiomatic fix is a `key` that changes every time the dialog opens,
 * so React remounts this component with a fresh `useState("")` instead of
 * an effect reconciling stale state after the fact -- `ReportActionsSlot`
 * supplies that key (an incrementing counter bumped on each "Ask about
 * another option" click).
 */
export function AskOtherDialog({
  isOpen,
  onClose,
  onSubmit,
  optionLabel,
  submitting,
  error,
}: AskOtherDialogProps) {
  const [message, setMessage] = useState("");
  const trimmed = message.trim();
  const canSubmit = trimmed.length >= 1 && trimmed.length <= MAX_MESSAGE_LENGTH;

  function handleClose() {
    if (submitting) return;
    onClose();
  }

  return (
    <Overlay
      isOpen={isOpen}
      onClose={handleClose}
      title="Ask about another option"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={handleClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={() => onSubmit(trimmed)} isLoading={submitting} disabled={!canSubmit}>
            Send message
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
        <p className="text-sm text-neutral-600">
          You&rsquo;re currently viewing <strong>{optionLabel}</strong>.
        </p>
        <label className="flex flex-col gap-1 text-sm text-navy-900">
          Your message
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="What would you like to change? For example, a lower cash to close."
            rows={4}
            maxLength={MAX_MESSAGE_LENGTH}
            className="rounded-md border border-neutral-300 p-2 text-sm text-navy-900"
          />
        </label>
      </div>
    </Overlay>
  );
}
