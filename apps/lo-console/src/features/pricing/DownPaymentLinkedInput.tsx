"use client";

import { MoneyInput, PercentInput } from "@cq/ui";

export interface DownPaymentLinkedInputProps {
  purchasePriceValue: string;
  onPurchasePriceChange: (value: string) => void;
  downPaymentPctValue: string;
  // percent-unit text (e.g. "20.000"), matching `PercentInput`'s own
  // contract -- `format.ts`'s conversion helpers translate to/from the
  // API's 0-1-fraction wire format at the call site (PricingPanel).
  onDownPaymentPctChange: (value: string) => void;
  downPaymentAmountValue: string;
  onDownPaymentAmountChange: (value: string) => void;
  loanAmountDisplay: string;
  ltvDisplay: string;
  disabled?: boolean;
}

// spec.md AC2: purchase price, down payment as a linked %/$ pair (editing
// either updates the other), and loan amount/LTV read-only. This component
// is deliberately "dumb": both `downPaymentPctValue`/`downPaymentAmountValue`
// are fully controlled by the caller (PricingPanel), which resolves the
// link server-side (`/quotes/preview`, debounced) and re-renders both
// fields from that single response -- neither field's displayed value is
// ever derived from the other in this component (AGENTS.md: money math
// lives only in `quote_engine`; see `pricing-no-money-math.test.ts`).
export function DownPaymentLinkedInput({
  purchasePriceValue,
  onPurchasePriceChange,
  downPaymentPctValue,
  onDownPaymentPctChange,
  downPaymentAmountValue,
  onDownPaymentAmountChange,
  loanAmountDisplay,
  ltvDisplay,
  disabled = false,
}: DownPaymentLinkedInputProps) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium text-neutral-600">Purchase price</span>
        <MoneyInput
          aria-label="Purchase price"
          value={purchasePriceValue}
          onChange={onPurchasePriceChange}
          disabled={disabled}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-neutral-600">Down payment %</span>
          <PercentInput
            aria-label="Down payment percent"
            value={downPaymentPctValue}
            onChange={onDownPaymentPctChange}
            disabled={disabled}
          />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-neutral-600">Down payment $</span>
          <MoneyInput
            aria-label="Down payment amount"
            value={downPaymentAmountValue}
            onChange={onDownPaymentAmountChange}
            disabled={disabled}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-neutral-600">Loan amount</span>
          <p className="num text-navy-900" aria-label="Loan amount">
            {loanAmountDisplay}
          </p>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-neutral-600">LTV</span>
          <p className="num text-navy-900" aria-label="LTV">
            {ltvDisplay}
          </p>
        </div>
      </div>
    </div>
  );
}
