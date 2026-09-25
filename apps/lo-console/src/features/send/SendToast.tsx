export interface SendToastProps {
  message: string | null;
  onDismiss: () => void;
}

/** "Sent to {email}" after a send finishes (it hides itself after a few
 * seconds; see `useSendFlow`). */
export function SendToast({ message, onDismiss }: SendToastProps) {
  if (message === null) return null;
  return (
    <div
      role="status"
      data-testid="send-toast"
      className="fixed right-4 bottom-4 z-50 flex items-center gap-3 rounded-md bg-navy-900 px-4 py-3 text-sm text-neutral-0 shadow-lg"
    >
      <span>{message}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="text-neutral-200 hover:text-neutral-0"
      >
        ×
      </button>
    </div>
  );
}
