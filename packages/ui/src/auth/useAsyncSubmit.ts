"use client";

import { useCallback, useState } from "react";

import { extractErrorMessage } from "./errors";

export type AsyncSubmitResult<TData> = { ok: true; data: TData } | { ok: false; error: unknown };

export interface UseAsyncSubmitOptions<TValues, TData> {
  // Shown when the rejected result's `error` doesn't match a shape
  // `extractErrorMessage` recognizes (network failure, 500, etc).
  fallbackError: string;
  onSuccess?: (data: TData, values: TValues) => void;
}

export interface UseAsyncSubmitResult<TValues> {
  pending: boolean;
  error: string | null;
  // Runs `submit`, owning the pending/error state around it. Never throws:
  // a rejected promise is treated the same as an `{ ok: false }` result.
  run: (values: TValues) => Promise<void>;
}

// Owns the pending/error/submit boilerplate every auth form (and any other
// async form) repeats: set pending, clear the previous error, call the
// caller's async `submit`, turn a `{ ok: false, error }` result (or a
// thrown error) into a displayable message, and always clear pending.
export function useAsyncSubmit<TValues, TData>(
  submit: (values: TValues) => Promise<AsyncSubmitResult<TData>>,
  { fallbackError, onSuccess }: UseAsyncSubmitOptions<TValues, TData>,
): UseAsyncSubmitResult<TValues> {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (values: TValues) => {
      setError(null);
      setPending(true);

      try {
        const result = await submit(values);

        if (!result.ok) {
          setError(extractErrorMessage(result.error, fallbackError));
          return;
        }

        onSuccess?.(result.data, values);
      } catch {
        setError(fallbackError);
      } finally {
        setPending(false);
      }
    },
    [submit, fallbackError, onSuccess],
  );

  return { pending, error, run };
}
