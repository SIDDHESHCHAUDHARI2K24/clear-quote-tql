// Pure list operations on the draft's quote ids (no money fields).

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
