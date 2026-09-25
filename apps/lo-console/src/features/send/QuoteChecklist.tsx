"use client";

import { useRef } from "react";

import { formatPercent } from "@cq/ui";

import { formatMoneyCents } from "../pricing/format";
import type { QuoteCardData, ScenariosView } from "../quote-builder/api";
import type { PackageUpdate, SendPackage } from "./api";
import { MAX_PACKAGE_QUOTES, moveItem, withQuoteAdded, withQuoteRemoved } from "./draft";

export interface QuoteChecklistProps {
  pkg: SendPackage;
  scenarios: ScenariosView;
  disabled?: boolean;
  onChange: (draft: PackageUpdate) => void;
}

interface CardEntry {
  card: QuoteCardData;
  group: string;
}

function quoteName({ card, group }: CardEntry): string {
  return `${card.label} ${formatPercent(card.rate_pct)} (${group})`;
}

function QuoteSummary({ entry }: { entry: CardEntry }) {
  const { card, group } = entry;
  return (
    <span className="flex min-w-0 flex-1 flex-col">
      <span className="font-medium text-navy-900">
        {card.label} {formatPercent(card.rate_pct)}
        {card.stale && (
          <span className="ml-2 rounded bg-status-warning/15 px-1.5 text-xs text-navy-900">
            Stale
          </span>
        )}
      </span>
      <span className="num text-xs text-neutral-600">
        {group} · {formatMoneyCents(card.monthly_payment)}/mo ·{" "}
        {formatMoneyCents(card.cash_to_close)} to close
      </span>
    </span>
  );
}

/** Selected quotes in send order (drag or move up/down), the recommended
 * radio, and the remaining priced quotes to add (at most 3 in total). */
export function QuoteChecklist({
  pkg,
  scenarios,
  disabled = false,
  onChange,
}: QuoteChecklistProps) {
  const dragIndex = useRef<number | null>(null);
  const entries = new Map<string, CardEntry>();
  for (const group of scenarios.groups) {
    for (const card of group.quotes) entries.set(card.id, { card, group: group.label });
  }
  const selected = pkg.quote_ids.filter((id) => entries.has(id));
  const selectedSet = new Set(selected);
  const others = [...entries.keys()].filter((id) => !selectedSet.has(id));
  const full = selected.length >= MAX_PACKAGE_QUOTES;
  const draft = (quoteIds: string[], recommended: string | null): PackageUpdate => ({
    quote_ids: quoteIds,
    recommended_quote_id: recommended,
    lo_note: pkg.lo_note ?? null,
  });

  const move = (from: number, to: number) => {
    if (to < 0 || to >= selected.length || from === to) return;
    onChange(draft(moveItem(selected, from, to), pkg.recommended_quote_id ?? null));
  };

  return (
    <fieldset className="flex flex-col gap-3" disabled={disabled}>
      <legend className="text-sm font-semibold text-navy-900">Quotes to send</legend>
      {selected.length === 0 && <p className="text-sm text-neutral-600">No quotes selected yet.</p>}
      <ol className="flex flex-col gap-2" aria-label="Selected quotes">
        {selected.map((id, index) => {
          const entry = entries.get(id)!;
          const name = quoteName(entry);
          return (
            <li
              key={id}
              data-testid="selected-quote"
              draggable={!disabled}
              onDragStart={() => {
                dragIndex.current = index;
              }}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => {
                if (dragIndex.current !== null) move(dragIndex.current, index);
                dragIndex.current = null;
              }}
              className="flex items-center gap-3 rounded-md border border-neutral-200 bg-neutral-0 px-3 py-2"
            >
              <span aria-hidden="true" className="cursor-grab text-neutral-400">
                ⋮⋮
              </span>
              <input
                type="checkbox"
                checked
                aria-label={`Include ${name}`}
                onChange={() => {
                  const next = withQuoteRemoved(selected, pkg.recommended_quote_id ?? null, id);
                  onChange(draft(next.quoteIds, next.recommended));
                }}
              />
              <QuoteSummary entry={entry} />
              <label className="flex items-center gap-1 text-xs text-navy-900">
                <input
                  type="radio"
                  name="recommended-quote"
                  checked={pkg.recommended_quote_id === id}
                  onChange={() => onChange(draft(selected, id))}
                  aria-label={`Recommend ${name}`}
                />
                Recommended
              </label>
              <span className="flex flex-col">
                <button
                  type="button"
                  className="px-1 text-xs text-navy-700 disabled:text-neutral-300"
                  aria-label={`Move ${name} up`}
                  disabled={index === 0}
                  onClick={() => move(index, index - 1)}
                >
                  ▲
                </button>
                <button
                  type="button"
                  className="px-1 text-xs text-navy-700 disabled:text-neutral-300"
                  aria-label={`Move ${name} down`}
                  disabled={index === selected.length - 1}
                  onClick={() => move(index, index + 1)}
                >
                  ▼
                </button>
              </span>
            </li>
          );
        })}
      </ol>
      {others.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-neutral-600">
            Other priced quotes{full ? ` (up to ${MAX_PACKAGE_QUOTES} per package)` : ""}
          </p>
          <ul className="flex flex-col gap-2" aria-label="Other quotes">
            {others.map((id) => {
              const entry = entries.get(id)!;
              const name = quoteName(entry);
              return (
                <li
                  key={id}
                  className="flex items-center gap-3 rounded-md border border-dashed border-neutral-200 px-3 py-2"
                >
                  <input
                    type="checkbox"
                    checked={false}
                    disabled={full}
                    aria-label={`Include ${name}`}
                    onChange={() => {
                      const next = withQuoteAdded(selected, pkg.recommended_quote_id ?? null, id);
                      onChange(draft(next.quoteIds, next.recommended));
                    }}
                  />
                  <QuoteSummary entry={entry} />
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </fieldset>
  );
}
