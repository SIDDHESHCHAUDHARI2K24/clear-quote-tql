"use client";

import { useEffect, useState } from "react";

import { previewQuote } from "./api";
import type { QuotePreviewRequest, QuotePreviewResponse } from "./api";

const DEBOUNCE_MS = 250;
// spec.md: "a subtle 'recalculating' state shows if a call takes > 300ms".
const RECALCULATING_DELAY_MS = 300;

export interface UsePricingPreviewResult {
  data: QuotePreviewResponse | null;
  isRecalculating: boolean;
  error: boolean;
}

// Two effects, each owning exactly one timer/subscription so cleanup is
// unambiguous:
//   1. Debounces `request` 250ms into `debouncedKey`.
//   2. Fires `POST /quotes/preview` whenever `debouncedKey` changes, using
//      one `AbortController` to both cancel a superseded request (out-of-
//      order responses are ignored via `signal.aborted`, not a separate
//      request-id counter) and as this effect's own cleanup.
export function usePricingPreview(request: QuotePreviewRequest | null): UsePricingPreviewResult {
  const [data, setData] = useState<QuotePreviewResponse | null>(null);
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [error, setError] = useState(false);
  const requestKey = request ? JSON.stringify(request) : null;
  const [debouncedKey, setDebouncedKey] = useState<string | null>(null);

  useEffect(() => {
    if (requestKey === null) {
      // Reset immediately (no debounce delay) so a fresh, non-live view
      // (e.g. right after an override's own reload) is never held behind
      // a stale in-flight preview result for up to 250ms.
      setDebouncedKey(null);
      return;
    }
    const timer = setTimeout(() => setDebouncedKey(requestKey), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [requestKey]);

  useEffect(() => {
    if (debouncedKey === null) {
      // No live edit in progress (e.g. just reloaded from the server) --
      // stop showing a stale preview result so the caller falls back to
      // the freshly fetched pricing view's own breakdown.
      setData(null);
      setIsRecalculating(false);
      setError(false);
      return;
    }

    const controller = new AbortController();
    const recalcTimer = setTimeout(() => setIsRecalculating(true), RECALCULATING_DELAY_MS);

    previewQuote(JSON.parse(debouncedKey) as QuotePreviewRequest, controller.signal)
      .then(({ data: responseData }) => {
        if (controller.signal.aborted) return; // superseded
        if (responseData) {
          // `responseData`'s inferred type and the `QuotePreviewResponse`
          // alias are structurally identical (both trace back to the same
          // OpenAPI `QuotePreviewResponse` schema, including
          // `config_snapshot`), but openapi-fetch's generic response
          // inference at this call site produces a separately-computed
          // instantiation that TS's structural checker (a known
          // limitation with deeply nested tuple types, here `ConfigSnapshot.
          // mi_matrix`) refuses to unify with the imported alias.
          setData(responseData as unknown as QuotePreviewResponse);
          setError(false);
        } else {
          setError(true);
        }
      })
      .catch(() => {
        if (controller.signal.aborted) return; // superseded/aborted
        setError(true);
      })
      .finally(() => {
        if (controller.signal.aborted) return;
        clearTimeout(recalcTimer);
        setIsRecalculating(false);
      });

    return () => {
      controller.abort();
      clearTimeout(recalcTimer);
    };
  }, [debouncedKey]);

  return { data, isRecalculating, error };
}
