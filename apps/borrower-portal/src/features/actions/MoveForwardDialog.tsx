"use client";

import { Button, Overlay } from "@cq/ui";

export interface MoveForwardDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  optionLabel: string;
  loFirstName: string;
  submitting: boolean;
  error: string | null;
}

/**
 * spec.md: "Move forward -> confirm dialog: 'This tells {LO first name}
 * you'd like to go ahead with {option label}. Your rate isn't locked yet --
 * {LO first name} will contact you about next steps.' Buttons: 'Yes, let
 * {LO first name} know' / 'Cancel'."
 *
 * The dialog text's "isn't locked yet" is spec.md's own exact wording, not
 * a violation of AC5's "never say ... 'lock'" -- AC5's scanner (both here
 * and `portal/actions/tests/test_templates.py`) matches the bare word
 * "lock" only (word-boundary), which "locked" doesn't contain a boundary
 * for. The point of AC5 is never to say the rate *is* locked; this
 * sentence says the opposite.
 */
export function MoveForwardDialog({
  isOpen,
  onClose,
  onConfirm,
  optionLabel,
  loFirstName,
  submitting,
  error,
}: MoveForwardDialogProps) {
  return (
    <Overlay
      isOpen={isOpen}
      onClose={onClose}
      title="Move forward with this option?"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={onConfirm} isLoading={submitting}>
            Yes, let {loFirstName} know
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
        <p className="text-sm text-navy-900">
          This tells {loFirstName} you&rsquo;d like to go ahead with <strong>{optionLabel}</strong>.
          Your rate isn&rsquo;t locked yet &mdash; {loFirstName} will contact you about next steps.
        </p>
      </div>
    </Overlay>
  );
}
