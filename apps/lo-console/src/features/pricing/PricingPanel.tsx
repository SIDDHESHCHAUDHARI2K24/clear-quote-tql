"use client";

import { useEffect, useMemo, useState } from "react";

import { Card } from "@cq/ui";

import { useWorkspace } from "../workspace";
import { fetchPricingView, patchFieldValueOverride, revertFieldValue } from "./api";
import type { PricingField, PricingView, QuoteComputation, QuotePreviewRequest } from "./api";
import { DownPaymentLinkedInput } from "./DownPaymentLinkedInput";
import { EnrichedMoneyField } from "./EnrichedMoneyField";
import { EnrichedPercentField } from "./EnrichedPercentField";
import {
  dscrTone,
  formatDscr2dp,
  formatMoneyCents,
  formatPercent2dp,
  formatRate3dp,
  fractionToPercentInputValue,
  percentInputValueToFraction,
} from "./format";
import { QuoteBuilderSlot } from "./QuoteBuilderSlot";
import { usePricingPreview } from "./usePricingPreview";

const DSCR_TONE_CLASS: Record<NonNullable<ReturnType<typeof dscrTone>>, string> = {
  green: "text-status-success",
  neutral: "text-navy-900",
  amber: "text-status-warning",
};

const PPP_OPTIONS = [
  { value: "", label: "None" },
  { value: "1", label: "1 year" },
  { value: "2", label: "2 years" },
  { value: "3", label: "3 years" },
  { value: "5", label: "5 years" },
];

type LoadState = { kind: "loading" } | { kind: "error" } | { kind: "ready"; view: PricingView };

type DownPaymentEditedField = "pct" | "amount" | null;

function fieldByKey(view: PricingView | null, key: string): PricingField | undefined {
  return view?.fields.find((f) => f.field_key === key);
}

export function PricingPanel() {
  const { applicationId, refetch: refetchWorkspace } = useWorkspace();
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  const [purchasePriceText, setPurchasePriceText] = useState("");
  const [downPaymentPctText, setDownPaymentPctText] = useState("");
  const [downPaymentAmountText, setDownPaymentAmountText] = useState("");
  const [downPaymentEdited, setDownPaymentEdited] = useState<DownPaymentEditedField>(null);
  const [dirty, setDirty] = useState(false);
  const [pppYears, setPppYears] = useState<string>("");

  const load = async () => {
    setState({ kind: "loading" });
    try {
      const { data } = await fetchPricingView(applicationId);
      if (!data) {
        setState({ kind: "error" });
        return;
      }
      // See the `breakdown` cast below: `data`'s inferred type and the
      // `PricingView` alias are structurally identical, but openapi-fetch's
      // per-call generic inference doesn't unify with the imported alias
      // for the nested `config_snapshot.mi_matrix` tuple type.
      setState({ kind: "ready", view: data as unknown as PricingView });
      setPurchasePriceText(data.inputs.purchase_price);
      setDownPaymentPctText(fractionToPercentInputValue(data.inputs.down_payment_pct));
      setDownPaymentAmountText(data.breakdown?.down_payment_amount ?? "");
      setPppYears(
        data.inputs.prepayment_penalty_years != null
          ? String(data.inputs.prepayment_penalty_years)
          : "",
      );
      setDownPaymentEdited(null);
      setDirty(false);
    } catch {
      setState({ kind: "error" });
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicationId]);

  const view = state.kind === "ready" ? state.view : null;

  const taxField = fieldByKey(view, "property_tax_annual_rate");
  const insuranceField = fieldByKey(view, "homeowners_ins_annual");
  const hoaField = fieldByKey(view, "hoa_fee_monthly");
  const rentField = fieldByKey(view, "market_rent_ltr");
  const strRevenueField = fieldByKey(view, "gross_annual_revenue_str");

  const previewRequest: QuotePreviewRequest | null = useMemo(() => {
    if (!view || !dirty) return null;
    if (view.note_rate === null || view.inputs.fico === null) return null;
    if (view.inputs.insurance_annual_rate === null) return null;
    if (!taxField?.value) return null;
    if (view.inputs.strategy === "LTR" && !rentField?.value) return null;
    if (view.inputs.strategy === "STR" && !strRevenueField?.value) return null;
    if (purchasePriceText === "") return null;

    const base = {
      purchase_price: purchasePriceText,
      note_rate: view.note_rate,
      strategy: view.inputs.strategy,
      fico: view.inputs.fico,
      property_tax_annual_rate: taxField.value,
      insurance_annual_rate: view.inputs.insurance_annual_rate,
      term_months: 360,
      hoa_monthly: hoaField?.value ?? "0",
      discount_points_pct: "0",
      seller_credits: "0",
      market_rent_ltr: view.inputs.strategy === "LTR" ? (rentField?.value ?? null) : null,
      str_gross_annual_revenue:
        view.inputs.strategy === "STR" ? (strRevenueField?.value ?? null) : null,
    };

    if (downPaymentEdited === "amount" && downPaymentAmountText !== "") {
      return { ...base, down_payment_amount: downPaymentAmountText };
    }
    const pctFraction = percentInputValueToFraction(downPaymentPctText);
    if (pctFraction === "") return null;
    return { ...base, down_payment_pct: pctFraction };
  }, [
    view,
    dirty,
    purchasePriceText,
    downPaymentPctText,
    downPaymentAmountText,
    downPaymentEdited,
    taxField,
    hoaField,
    rentField,
    strRevenueField,
  ]);

  const preview = usePricingPreview(previewRequest);

  // Once a fresh preview response arrives, resync both sides of the
  // down-payment link from it (never derived locally -- straight from the
  // API response's own `down_payment_pct`/`down_payment_amount`).
  useEffect(() => {
    if (!preview.data) return;
    setDownPaymentPctText(fractionToPercentInputValue(preview.data.down_payment_pct));
    setDownPaymentAmountText(preview.data.down_payment_amount);
  }, [preview.data]);

  // See `usePricingPreview.ts`'s comment on the same cast: `preview.data`
  // and `view.breakdown` are structurally the same `QuoteComputation`
  // shape (both come from the same backend `QuoteComputation.model_dump()`),
  // but trace through two separately-typed API calls (`/quotes/preview` vs
  // `/applications/{id}/pricing`) whose independently-inferred response
  // types TS's structural checker won't unify (the nested `config_snapshot.
  // mi_matrix` tuple type).
  const breakdown: QuoteComputation | null =
    (preview.data as unknown as QuoteComputation | null) ?? view?.breakdown ?? null;

  const handleOverride = async (fieldKey: string, value: string) => {
    const result = await patchFieldValueOverride(applicationId, fieldKey, value);
    if (result.data) {
      await load();
      await refetchWorkspace();
    }
  };

  const handleRevert = async (fieldKey: string) => {
    const result = await revertFieldValue(applicationId, fieldKey);
    if (result.data) {
      await load();
      await refetchWorkspace();
    }
  };

  if (state.kind === "loading") {
    return (
      <div role="status" aria-label="Loading pricing" className="animate-pulse">
        <div className="h-64 rounded bg-neutral-100" />
      </div>
    );
  }
  if (state.kind === "error" || !view) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-sm text-neutral-600">Couldn&apos;t load pricing for this application.</p>
        <button
          type="button"
          onClick={() => void load()}
          className="text-sm font-medium text-navy-500 hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  const strategy = view.inputs.strategy;
  const isPrimary = strategy === "PRIMARY";
  const showMi = isPrimary && breakdown?.monthly_mi != null;
  const dscrToneValue = dscrTone(breakdown?.dscr_ratio ?? null);

  return (
    // No `<main>` landmark exists anywhere else in the `/applications/[id]/**`
    // tree (WorkspaceShell's body is a plain `<div>`, owned by CQ-016, out
    // of this item's scope to change) -- wrapping this tab's own content in
    // one here satisfies axe's "region" rule for every element this item
    // owns without touching another item's files.
    <main aria-label="Pricing" className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Loan structure">
          <div className="flex flex-col gap-4">
            <DownPaymentLinkedInput
              purchasePriceValue={purchasePriceText}
              onPurchasePriceChange={(v) => {
                setPurchasePriceText(v);
                setDirty(true);
              }}
              downPaymentPctValue={downPaymentPctText}
              onDownPaymentPctChange={(v) => {
                setDownPaymentPctText(v);
                setDownPaymentEdited("pct");
                setDirty(true);
              }}
              downPaymentAmountValue={downPaymentAmountText}
              onDownPaymentAmountChange={(v) => {
                setDownPaymentAmountText(v);
                setDownPaymentEdited("amount");
                setDirty(true);
              }}
              loanAmountDisplay={formatMoneyCents(breakdown?.loan_amount ?? null)}
              ltvDisplay={formatPercent2dp(breakdown?.ltv_pct ?? null)}
            />
            {!isPrimary && (
              <div className="flex flex-col gap-1">
                <label htmlFor="ppp-select" className="text-xs font-medium text-neutral-600">
                  Prepayment penalty
                </label>
                <select
                  id="ppp-select"
                  className="rounded-md border border-neutral-200 bg-neutral-0 px-2 py-2 text-sm text-navy-900"
                  value={pppYears}
                  onChange={(e) => setPppYears(e.target.value)}
                >
                  {PPP_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-neutral-600">Note rate</span>
              <p className="num text-navy-900" aria-label="Note rate">
                {formatRate3dp(view.note_rate)}
              </p>
            </div>
          </div>
        </Card>

        <Card
          title="Payment breakdown"
          actions={
            preview.isRecalculating ? (
              <span className="text-xs text-neutral-500">Recalculating…</span>
            ) : undefined
          }
        >
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-neutral-600">P&amp;I</span>
              <span className="num text-navy-900">
                {formatMoneyCents(breakdown?.monthly_pi ?? null)}
              </span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-neutral-600">Taxes (monthly)</span>
              <span className="num text-navy-900">
                {formatMoneyCents(breakdown?.monthly_tax ?? null)}
              </span>
            </div>
            <EnrichedPercentField
              label="Tax annual rate"
              ariaLabel="Property tax annual rate"
              field={taxField}
              onOverride={(v) => void handleOverride("property_tax_annual_rate", v)}
              onRevert={() => void handleRevert("property_tax_annual_rate")}
            />
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-neutral-600">Insurance (monthly)</span>
              <span className="num text-navy-900">
                {formatMoneyCents(breakdown?.monthly_insurance ?? null)}
              </span>
            </div>
            <EnrichedMoneyField
              label="Insurance annual premium"
              ariaLabel="Homeowners insurance annual premium"
              field={insuranceField}
              onOverride={(v) => void handleOverride("homeowners_ins_annual", v)}
              onRevert={() => void handleRevert("homeowners_ins_annual")}
            />
            {showMi && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-neutral-600">MI</span>
                <span className="num text-navy-900">
                  {formatMoneyCents(breakdown?.monthly_mi ?? null)}
                </span>
              </div>
            )}
            <EnrichedMoneyField
              label="HOA (monthly)"
              ariaLabel="HOA monthly fee"
              field={hoaField}
              onOverride={(v) => void handleOverride("hoa_fee_monthly", v)}
              onRevert={() => void handleRevert("hoa_fee_monthly")}
            />
            <div className="flex items-center justify-between border-t border-neutral-200 pt-3">
              <span className="text-md font-semibold text-navy-900">Total monthly payment</span>
              <span className="num text-lg font-semibold text-navy-900">
                {formatMoneyCents(breakdown?.total_monthly_payment ?? null)}
              </span>
            </div>
          </div>
        </Card>
      </div>

      {!isPrimary && (
        <Card title={strategy === "LTR" ? "Long-term rental" : "Short-term rental"}>
          <div className="flex flex-col gap-4">
            {strategy === "LTR" && (
              <EnrichedMoneyField
                label="Market rent (monthly)"
                ariaLabel="Market rent"
                field={rentField}
                onOverride={(v) => void handleOverride("market_rent_ltr", v)}
                onRevert={() => void handleRevert("market_rent_ltr")}
              />
            )}
            {strategy === "STR" && (
              <>
                <EnrichedMoneyField
                  label="Gross annual STR revenue"
                  ariaLabel="Gross annual STR revenue"
                  field={strRevenueField}
                  onOverride={(v) => void handleOverride("gross_annual_revenue_str", v)}
                  onRevert={() => void handleRevert("gross_annual_revenue_str")}
                />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-neutral-600">Gross monthly revenue</span>
                  <span className="num text-navy-900">
                    {formatMoneyCents(breakdown?.str_gross_monthly_revenue ?? null)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-neutral-600">Expense ratio</span>
                  <span className="num text-navy-900">
                    {formatPercent2dp(breakdown?.config_snapshot.str_expense_ratio ?? null)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-neutral-600">Underwritten rent</span>
                  <span className="num text-navy-900">
                    {formatMoneyCents(breakdown?.underwritten_str_rent ?? null)}
                  </span>
                </div>
              </>
            )}
            <div className="flex items-center justify-between">
              <span className="text-sm text-neutral-600">DSCR</span>
              <span
                className={`num font-semibold ${dscrToneValue ? DSCR_TONE_CLASS[dscrToneValue] : "text-navy-900"}`}
                aria-label="DSCR"
              >
                {formatDscr2dp(breakdown?.dscr_ratio ?? null)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-neutral-600">Break-even rent</span>
              <span className="num text-navy-900">
                {formatMoneyCents(
                  strategy === "LTR"
                    ? (breakdown?.break_even_rent_ltr ?? null)
                    : (breakdown?.str_annual_rent_target ?? null),
                )}
              </span>
            </div>
          </div>
        </Card>
      )}

      <Card title="Cash to close">
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-neutral-600">Down payment</span>
            <span className="num text-navy-900">
              {formatMoneyCents(breakdown?.down_payment_amount ?? null)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-neutral-600">Lender fees</span>
            <span className="num text-navy-900">
              {formatMoneyCents(breakdown?.lender_fees ?? null)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-neutral-600">Discount points</span>
            <span className="num text-navy-900">
              {formatMoneyCents(breakdown?.discount_points_amount ?? null)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-neutral-600">Title</span>
            <span className="num text-navy-900">
              {formatMoneyCents(breakdown?.title_fees ?? null)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-neutral-600">Prepaids</span>
            <span className="num text-navy-900">
              {formatMoneyCents(breakdown?.total_prepaids ?? null)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-neutral-600">Credits</span>
            <span className="num text-navy-900">{formatMoneyCents("0.00")}</span>
          </div>
          <div className="flex items-center justify-between border-t border-neutral-200 pt-3">
            <span className="text-md font-semibold text-navy-900">Cash to close</span>
            <span className="num text-lg font-semibold text-navy-900">
              {formatMoneyCents(breakdown?.cash_to_close ?? null)}
            </span>
          </div>
          <p className="text-xs text-neutral-500">
            Appraisal ~$600–900, paid before closing (not included above).
          </p>
        </div>
      </Card>

      <QuoteBuilderSlot hasStaleQuotes={view.has_stale_quotes} />
    </main>
  );
}
