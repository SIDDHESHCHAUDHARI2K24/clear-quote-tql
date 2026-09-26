import { formatPercent, isNegative } from "@cq/ui";

import { formatMoneyCents } from "../pricing/format";
import type { BuilderStrategy, QuoteCardData } from "./api";

export interface QuoteCardProps {
  quote: QuoteCardData;
  strategy: BuilderStrategy | null;
  busy: boolean;
  selected: boolean;
  selectDisabled: boolean;
  onRecommend: (quoteId: string) => void;
  onEdit: () => void;
  onDelete: (quoteId: string) => void;
  onToggleCompare: (quoteId: string) => void;
}

function Row({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-neutral-600">{label}</dt>
      <dd className={`num text-right text-navy-900 ${tone ?? ""}`}>{value}</dd>
    </div>
  );
}

/**
 * One priced option. Every figure is a string from the API (the quote's own
 * engine output, scaled server-side); this component only formats it.
 * Primary cards never show DSCR, cashflow or PPP (AGENTS.md).
 */
export function QuoteCard({
  quote,
  strategy,
  busy,
  selected,
  selectDisabled,
  onRecommend,
  onEdit,
  onDelete,
  onToggleCompare,
}: QuoteCardProps) {
  const isInvestment = strategy === "LTR" || strategy === "STR";
  const isCredit = isNegative(quote.points_pct);
  const title = `${quote.label} ${formatPercent(quote.rate_pct)}`;

  return (
    <article
      aria-label={`${quote.label} quote`}
      data-quote-id={quote.id}
      data-priced-at={quote.priced_at}
      data-stale={quote.stale ? "true" : "false"}
      aria-busy={busy}
      className={`flex flex-col gap-3 rounded-lg border bg-neutral-0 p-4 ${
        quote.recommended ? "border-sage-500 ring-1 ring-sage-500" : "border-neutral-200"
      } ${busy ? "animate-pulse opacity-60" : ""}`}
    >
      <header className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-neutral-600">{quote.label}</p>
          <p className="num text-2xl font-semibold text-navy-900">
            {formatPercent(quote.rate_pct)}
          </p>
        </div>
        <button
          type="button"
          aria-label={quote.recommended ? `${title} is recommended` : `Recommend ${title}`}
          aria-pressed={quote.recommended}
          disabled={busy}
          onClick={() => onRecommend(quote.id)}
          className={`rounded-md px-2 py-1 text-lg leading-none ${
            quote.recommended ? "text-sage-500" : "text-neutral-400 hover:text-sage-500"
          }`}
        >
          {quote.recommended ? "★" : "☆"}
        </button>
      </header>

      {quote.recommended && <p className="text-xs font-medium text-sage-700">Recommended</p>}
      {quote.stale && (
        <p className="text-xs font-medium text-status-warning">Out of date — re-price</p>
      )}

      <dl className="flex flex-col gap-1 text-sm">
        <Row
          label="Points"
          value={`${formatPercent(quote.points_pct)} (${formatMoneyCents(quote.points_amount)})`}
          tone={isCredit ? "text-status-success" : undefined}
        />
        <Row label="Monthly payment" value={formatMoneyCents(quote.monthly_payment)} />
        <Row label="Cash to close" value={formatMoneyCents(quote.cash_to_close)} />
        {isInvestment && (
          <>
            <Row label="DSCR" value={quote.dscr_ratio ?? "—"} />
            <Row
              label="Monthly cashflow"
              value={formatMoneyCents(quote.monthly_cashflow)}
              tone={
                quote.monthly_cashflow && isNegative(quote.monthly_cashflow)
                  ? "text-status-danger"
                  : undefined
              }
            />
          </>
        )}
      </dl>

      <p className="text-xs text-neutral-600">
        {quote.investor} · {quote.product} · {quote.lock_days}-day lock
      </p>

      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-neutral-100 pt-3">
        <label className="flex items-center gap-2 text-xs text-neutral-600">
          <input
            type="checkbox"
            checked={selected}
            disabled={selectDisabled && !selected}
            onChange={() => onToggleCompare(quote.id)}
            aria-label={`Compare ${title}`}
          />
          Compare
        </label>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onEdit}
            disabled={busy}
            aria-label={`Edit ${title}`}
            className="rounded-md border border-neutral-200 px-2 py-1 text-xs font-medium text-navy-900"
          >
            Edit
          </button>
          <button
            type="button"
            onClick={() => onDelete(quote.id)}
            disabled={busy}
            aria-label={`Delete ${title}`}
            className="rounded-md border border-neutral-200 px-2 py-1 text-xs font-medium text-status-danger"
          >
            Delete
          </button>
        </div>
      </footer>
    </article>
  );
}
