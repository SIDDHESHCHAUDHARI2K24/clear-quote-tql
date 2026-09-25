// AC2: "Typing 25% in down payment updates the $ field to $85,500.00 and
// the breakdown within one debounce cycle; typing $68,400 sets 20.00%."
//
// `DownPaymentLinkedInput` itself is a "dumb" controlled component (see its
// own file's comment): neither of its two fields ever derives the other
// locally. This test proves the *linking* behaviour end to end with a
// small harness that mimics exactly what `PricingPanel` does -- resolve
// the link through a (here, fake/synchronous) server call and re-render
// both fields from that single response -- so the AC is exercised as a
// real interaction, not just prop plumbing.
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { DownPaymentLinkedInput } from "./DownPaymentLinkedInput";
import { fractionToPercentInputValue, percentInputValueToFraction } from "./format";

const PURCHASE_PRICE = "342000.00";

// A tiny stand-in for the server-side %<->$ resolution `/quotes/preview`
// performs (quote_engine.down_payment_pct_from_amount / purchase_price *
// down_payment_pct) -- kept here only so the harness can simulate "the
// debounced response comes back", never used to derive a value the
// component itself displays without a round trip.
function resolveLink(
  purchasePrice: string,
  pctFraction: string | null,
  amount: string | null,
): { down_payment_pct: string; down_payment_amount: string } {
  const price = Number(purchasePrice);
  if (pctFraction !== null) {
    const amt = (Number(pctFraction) * price).toFixed(2);
    return { down_payment_pct: pctFraction, down_payment_amount: amt };
  }
  const pct = (Number(amount) / price).toFixed(4);
  return { down_payment_pct: pct, down_payment_amount: amount as string };
}

function Harness() {
  const [pct, setPct] = useState(fractionToPercentInputValue("0.20"));
  const [amount, setAmount] = useState("68400.00");

  return (
    <DownPaymentLinkedInput
      purchasePriceValue={PURCHASE_PRICE}
      onPurchasePriceChange={() => {}}
      downPaymentPctValue={pct}
      onDownPaymentPctChange={(v) => {
        setPct(v);
        const fraction = percentInputValueToFraction(v);
        if (fraction === "") return;
        const resolved = resolveLink(PURCHASE_PRICE, fraction, null);
        setAmount(resolved.down_payment_amount);
      }}
      downPaymentAmountValue={amount}
      onDownPaymentAmountChange={(v) => {
        setAmount(v);
        if (v === "") return;
        const resolved = resolveLink(PURCHASE_PRICE, null, v);
        setPct(fractionToPercentInputValue(resolved.down_payment_pct));
      }}
      loanAmountDisplay="$273,600.00"
      ltvDisplay="80.00%"
    />
  );
}

describe("DownPaymentLinkedInput (AC2)", () => {
  it("typing 25% in down payment updates the $ field to $85,500.00", async () => {
    render(<Harness />);
    const pctInput = screen.getByLabelText("Down payment percent");

    await act(async () => {
      await userEvent.clear(pctInput);
      await userEvent.type(pctInput, "25");
    });

    const amountInput = screen.getByLabelText("Down payment amount") as HTMLInputElement;
    expect(amountInput.value).toBe("85500.00");
  });

  it("typing $68,400 sets the percent field to 20.00%", async () => {
    render(<Harness />);
    const amountInput = screen.getByLabelText("Down payment amount");

    await act(async () => {
      await userEvent.clear(amountInput);
      await userEvent.type(amountInput, "68400");
    });

    const pctInput = screen.getByLabelText("Down payment percent") as HTMLInputElement;
    expect(pctInput.value).toBe("20.000");
  });

  it("purchase price, loan amount and LTV render as passed (never computed in this component)", () => {
    render(<Harness />);
    expect(screen.getByLabelText("Purchase price")).toHaveValue(PURCHASE_PRICE);
    expect(screen.getByLabelText("Loan amount")).toHaveTextContent("$273,600.00");
    expect(screen.getByLabelText("LTV")).toHaveTextContent("80.00%");
  });

  it("every input is keyboard-accessible and labelled", () => {
    render(<Harness />);
    for (const label of ["Purchase price", "Down payment percent", "Down payment amount"]) {
      const input = screen.getByLabelText(label);
      expect(input).toBeVisible();
      input.focus();
      expect(input).toHaveFocus();
    }
  });
});
