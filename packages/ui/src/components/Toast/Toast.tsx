"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";

import { cx } from "../../utils/cx";

export type ToastTone = "success" | "info" | "warning" | "danger";

export interface ToastOptions {
  tone?: ToastTone;
  /** Auto-dismiss delay in ms (default 4000); `0` keeps it until closed. */
  durationMs?: number;
}

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

export interface ToastApi {
  show: (message: string, options?: ToastOptions) => number;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const TONE_CLASSES: Record<ToastTone, string> = {
  success: "border-status-success",
  info: "border-status-info",
  warning: "border-status-warning",
  danger: "border-status-danger",
};

export const DEFAULT_TOAST_DURATION_MS = 4000;

/**
 * Hosts transient notifications ("Saved", "Re-verify started") for its
 * subtree. The live region is always mounted (`role="status"`,
 * `aria-live="polite"`) so screen readers announce each new message.
 * Components call `useToast().show(message, { tone })`.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer) clearTimeout(timer);
    timers.current.delete(id);
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const show = useCallback(
    (message: string, options: ToastOptions = {}) => {
      const id = nextId.current++;
      setToasts((current) => [...current, { id, message, tone: options.tone ?? "info" }]);
      const duration = options.durationMs ?? DEFAULT_TOAST_DURATION_MS;
      if (duration > 0) {
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), duration),
        );
      }
      return id;
    },
    [dismiss],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach((timer) => clearTimeout(timer));
      pending.clear();
    };
  }, []);

  const api = useMemo<ToastApi>(() => ({ show, dismiss }), [show, dismiss]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed right-4 bottom-4 z-[60] flex max-w-[calc(100vw-2rem)] flex-col gap-2"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cx(
              "pointer-events-auto flex items-start gap-3 rounded-md border-l-4 bg-neutral-0 px-4 py-3 text-sm text-navy-900 shadow-lg",
              TONE_CLASSES[toast.tone],
            )}
          >
            <p className="flex-1">{toast.message}</p>
            <button
              type="button"
              aria-label="Dismiss notification"
              onClick={() => dismiss(toast.id)}
              className="text-neutral-600 hover:text-navy-900"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/** The nearest `ToastProvider`'s API. Throws outside a provider. */
export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast must be used inside a <ToastProvider>");
  return api;
}
