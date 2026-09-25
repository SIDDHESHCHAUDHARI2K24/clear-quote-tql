"use client";

import { Button, MoneyInput, Overlay, PercentInput } from "@cq/ui";
import { useMemo, useRef, useState } from "react";

import type { QuotePreviewRequest } from "../pricing/api";
import {
  formatMoneyCents,
  fractionToPercentInputValue,
  percentInputValueToFraction,
} from "../pricing/format";
import { usePricingPreview } from "../pricing/usePricingPreview";
import {
  autoquote,
  createScenario,
  updateScenario,
  type BuilderStrategy,
  type DscrBucket,
  type PricingProblem,
  type Result,
  type ScenarioGroup,
  type ScenarioUpdate,
} from "./api";
import { PricingProblemNotice } from "./PricingProblemNotice";

export type OverlayMode =
  { kind: "edit"; group: ScenarioGroup } | { kind: "add"; base: ScenarioGroup | null };

export interface ScenarioOverlayProps {
  applicationId: string;
  strategy: BuilderStrategy | null;
  mode: OverlayMode;
  onClose: () => void;
  /** After a successful Save & AutoQuote: refresh cards + header. */
  onSaved: () => Promise<void>;
  /** After inputs are saved: open the manual grid for that scenario. */
  onChooseManually: (scenarioId: string) => Promise<void>;
}

const LOCK_OPTIONS = [15, 30, 45, 60];
const PPP_OPTIONS = [0, 1, 2, 3, 4, 5];
const BUCKET_OPTIONS: { value: DscrBucket; label: string }[] = [
  { value: "BELOW_1_00", label: "Below 1.00" },
  { value: "ONE_TO_1_25", label: "1.00 to 1.24" },
  { value: "GE_1_25", label: "1.25 and above" },
];
const STRATEGY_NAMES: Record<BuilderStrategy, string> = {
  PRIMARY: "Primary residence",
  LTR: "Long-term rental",
  STR: "Short-term rental",
};

function isDecimalText(value: string): boolean {
  return /^\d+(\.\d+)?$/.test(value) && Number(value) > 0;
}

type Decimalish = string | number | null | undefined;

/** Decimal strings compared by value ("0.2" === "0.20"); equality only. */
function sameDecimal(a: Decimalish, b: Decimalish): boolean {
  if (a == null || b == null) return a == b;
  return Number(a) === Number(b);
}

/** Whether the overlay's inputs equal the saved scenario's (the server
 * applies the same defaults: lock 30 days, investment PPP 5 years). */
function sameAsSaved(group: ScenarioGroup, next: ScenarioUpdate): boolean {
  const saved = group.inputs;
  const savedPpp =
    next.prepayment_penalty_years == null ? null : (saved.prepayment_penalty_years ?? 5);
  return (
    sameDecimal(saved.purchase_price, next.purchase_price) &&
    sameDecimal(saved.down_payment_pct, next.down_payment_pct) &&
    saved.lock_days === next.lock_days &&
    savedPpp === (next.prepayment_penalty_years ?? null) &&
    (next.dscr_bucket == null || next.dscr_bucket === group.dscr_bucket)
  );
}

/**
 * Add/Edit scenario overlay (spec: every pricing input, a live preview of
 * payment and cash to close, and Save & AutoQuote / Choose manually).
 * Inputs start from the saved scenario, not the panel's unsaved draft
 * (plan.md Decision 9); Save persists them via PUT (or POST for Add).
 */
export function ScenarioOverlay({
  applicationId,
  strategy,
  mode,
  onClose,
  onSaved,
  onChooseManually,
}: ScenarioOverlayProps) {
  const group = mode.kind === "edit" ? mode.group : mode.base;
  const isInvestment = strategy === "LTR" || strategy === "STR";

  const [price, setPrice] = useState(group?.inputs.purchase_price ?? "");
  const [downPct, setDownPct] = useState(
    group ? fractionToPercentInputValue(group.inputs.down_payment_pct) : "",
  );
  const [ppp, setPpp] = useState(String(group?.inputs.prepayment_penalty_years ?? 5));
  const [lockDays, setLockDays] = useState(String(group?.inputs.lock_days ?? 30));
  const [bucket, setBucket] = useState<string>(
    mode.kind === "edit" ? (mode.group.dscr_bucket ?? "") : "",
  );
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<PricingProblem | null>(null);
  // Only read inside handlers, never rendered: a ref, not state.
  const createdId = useRef<string | null>(null);

  const downFraction = downPct === "" ? "" : percentInputValueToFraction(downPct);
  const valid = isDecimalText(price) && downFraction !== "" && isDecimalText(downPct);

  const anchor = group?.quotes.find((q) => q.label === "Par") ?? group?.quotes[0] ?? null;
  const previewRequest: QuotePreviewRequest | null = useMemo(() => {
    if (!group || !anchor || !valid) return null;
    return {
      ...(group.engine_inputs as unknown as QuotePreviewRequest),
      purchase_price: price,
      down_payment_pct: downFraction,
      note_rate: anchor.note_rate,
      discount_points_pct: anchor.discount_points_pct,
    };
  }, [group, anchor, valid, price, downFraction]);
  const preview = usePricingPreview(previewRequest);

  const body = (): ScenarioUpdate => ({
    purchase_price: price,
    down_payment_pct: downFraction,
    lock_days: Number(lockDays),
    prepayment_penalty_years: isInvestment ? Number(ppp) : null,
    dscr_bucket: isInvestment && bucket !== "" ? (bucket as DscrBucket) : null,
  });

  const persist = async ({ skipIfUnchanged = false } = {}): Promise<Result<string>> => {
    let scenarioId: string;
    if (mode.kind === "edit") {
      scenarioId = mode.group.id;
      // PR review (minor 2): opening the grid with untouched inputs must
      // not PUT (a PUT that changes inputs marks every quote stale).
      if (skipIfUnchanged && sameAsSaved(mode.group, body())) return { ok: true, data: scenarioId };
    } else if (createdId.current !== null) {
      // Add mode, retrying after a later step failed: reuse the scenario
      // the first attempt created instead of creating another one.
      scenarioId = createdId.current;
    } else {
      const created = await createScenario(applicationId, {
        purchase_price: price,
        down_payment_pct: downFraction,
        strategy: strategy ?? "PRIMARY",
        prepayment_penalty_years: isInvestment ? Number(ppp) : null,
      });
      if (!created.ok) return created;
      scenarioId = created.data.id;
      createdId.current = scenarioId;
    }
    const updated = await updateScenario(scenarioId, body());
    return updated.ok ? { ok: true, data: scenarioId } : updated;
  };

  const submit = async (
    next: (scenarioId: string) => Promise<Result<unknown>>,
    options: { skipIfUnchanged?: boolean } = {},
  ) => {
    if (!valid) {
      setProblem({ message: "Enter a purchase price and down payment.", field: null, tab: null });
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      const saved = await persist(options);
      if (!saved.ok) {
        setProblem(saved.problem);
        return;
      }
      const result = await next(saved.data);
      if (!result.ok) {
        setProblem(result.problem);
        await onSaved();
      }
    } finally {
      setBusy(false);
    }
  };

  const saveAndAutoquote = () =>
    submit(async (scenarioId) => {
      const result = await autoquote(scenarioId);
      if (result.ok) {
        await onSaved();
        onClose();
      }
      return result;
    });

  const chooseManually = () =>
    submit(
      async (scenarioId) => {
        await onChooseManually(scenarioId);
        return { ok: true, data: null };
      },
      { skipIfUnchanged: true },
    );

  return (
    <Overlay
      isOpen
      onClose={onClose}
      size="lg"
      title={mode.kind === "edit" ? `Edit scenario — ${mode.group.label}` : "Add scenario"}
      footer={
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="secondary" onClick={chooseManually} disabled={busy}>
            Choose manually
          </Button>
          <Button onClick={saveAndAutoquote} isLoading={busy}>
            Save &amp; AutoQuote
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        {problem && <PricingProblemNotice applicationId={applicationId} problem={problem} />}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1 text-sm">
            <span className="text-neutral-600">Purchase price</span>
            <MoneyInput aria-label="Purchase price" value={price} onChange={setPrice} />
          </div>
          <div className="flex flex-col gap-1 text-sm">
            <span className="text-neutral-600">Down payment</span>
            <PercentInput aria-label="Down payment percent" value={downPct} onChange={setDownPct} />
          </div>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-neutral-600">Lock days</span>
            <select
              value={lockDays}
              onChange={(e) => setLockDays(e.target.value)}
              className="rounded-md border border-neutral-200 px-3 py-2"
            >
              {LOCK_OPTIONS.map((days) => (
                <option key={days} value={days}>
                  {days} days
                </option>
              ))}
            </select>
          </label>
          {isInvestment && (
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-neutral-600">Prepayment penalty</span>
              <select
                value={ppp}
                onChange={(e) => setPpp(e.target.value)}
                className="rounded-md border border-neutral-200 px-3 py-2"
              >
                {PPP_OPTIONS.map((years) => (
                  <option key={years} value={years}>
                    {years === 0 ? "None" : `${years} years`}
                  </option>
                ))}
              </select>
            </label>
          )}
          {isInvestment && (
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-neutral-600">Assumed DSCR bucket</span>
              <select
                value={bucket}
                onChange={(e) => setBucket(e.target.value)}
                className="rounded-md border border-neutral-200 px-3 py-2"
              >
                <option value="">
                  {mode.kind === "edit" ? "Keep current" : "Computed from rent"}
                </option>
                {BUCKET_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="flex flex-col gap-1 text-sm">
            <span className="text-neutral-600">Strategy</span>
            <span className="py-2 text-navy-900">
              {strategy ? STRATEGY_NAMES[strategy] : "Not set"}
            </span>
          </div>
          <div className="flex flex-col gap-1 text-sm">
            <span className="text-neutral-600">FICO (from credit)</span>
            <span className="num py-2 text-navy-900">{group?.inputs.fico ?? "—"}</span>
          </div>
        </div>

        <div
          aria-live="polite"
          className="grid grid-cols-2 gap-3 rounded-md bg-neutral-50 p-3 text-sm"
        >
          <div>
            <p className="text-neutral-600">Monthly payment</p>
            <p
              className="num text-lg font-semibold text-navy-900"
              aria-label="Preview monthly payment"
            >
              {formatMoneyCents(preview.data?.total_monthly_payment ?? null)}
            </p>
          </div>
          <div>
            <p className="text-neutral-600">Cash to close</p>
            <p
              className="num text-lg font-semibold text-navy-900"
              aria-label="Preview cash to close"
            >
              {formatMoneyCents(preview.data?.cash_to_close ?? null)}
            </p>
          </div>
          <p className="col-span-2 text-xs text-neutral-600">
            {anchor
              ? `Preview at the current ${anchor.label} rate; Save & AutoQuote re-prices.`
              : "Preview appears once this scenario has a priced quote."}
          </p>
        </div>
      </div>
    </Overlay>
  );
}
