// Pure list operations on the draft's quote ids (no money fields).

import type { PackageUpdate, SendPackage } from "./api";

/** Matches the backend's `MAX_PACKAGE_QUOTES` (the recommended quote plus
 * up to 2 alternatives). */
export const MAX_PACKAGE_QUOTES = 3;

export interface Selection {
  quoteIds: string[];
  recommended: string | null;
}

export function moveItem<T>(items: T[], from: number, to: number): T[] {
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

/** Removing the recommended quote hands the recommendation to the first
 * quote left, so a package with quotes always has one. */
export function withQuoteRemoved(
  quoteIds: string[],
  recommended: string | null,
  id: string,
): Selection {
  const next = quoteIds.filter((q) => q !== id);
  return {
    quoteIds: next,
    recommended: recommended === id || recommended === null ? (next[0] ?? null) : recommended,
  };
}

export function withQuoteAdded(
  quoteIds: string[],
  recommended: string | null,
  id: string,
): Selection {
  if (quoteIds.includes(id) || quoteIds.length >= MAX_PACKAGE_QUOTES) {
    return { quoteIds, recommended };
  }
  return { quoteIds: [...quoteIds, id], recommended: recommended ?? id };
}

/** The `PackageUpdate` fields `draft` changes relative to `base` (the
 * caller's own snapshot when it built `draft`) -- e.g. `{ lo_note: "..." }`
 * when only the note changed. Used to replay just the caller's intended
 * edit onto whatever the latest confirmed server state turns out to be
 * (M1, post-merge review): two saves fired close together must not undo
 * each other by each PUTting a full draft built from a state the other
 * has already moved past. */
export function editedPackageFields(
  draft: PackageUpdate,
  base: Pick<SendPackage, "quote_ids" | "recommended_quote_id" | "lo_note">,
): Partial<PackageUpdate> {
  const edit: Partial<PackageUpdate> = {};
  if (
    draft.quote_ids.length !== base.quote_ids.length ||
    draft.quote_ids.some((id, index) => id !== base.quote_ids[index])
  ) {
    edit.quote_ids = draft.quote_ids;
  }
  if ((draft.recommended_quote_id ?? null) !== (base.recommended_quote_id ?? null)) {
    edit.recommended_quote_id = draft.recommended_quote_id ?? null;
  }
  if ((draft.lo_note ?? null) !== (base.lo_note ?? null)) {
    edit.lo_note = draft.lo_note ?? null;
  }
  return edit;
}
