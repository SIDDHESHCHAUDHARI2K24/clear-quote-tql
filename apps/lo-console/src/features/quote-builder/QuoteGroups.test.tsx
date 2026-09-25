import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ScenariosView } from "./api";
import danielFixture from "./__fixtures__/scenarios-daniel-ortiz.json";
import kathleenFixture from "./__fixtures__/scenarios-kathleen-mcreynolds.json";
import marcusFixture from "./__fixtures__/scenarios-marcus-hale.json";
import priyaFixture from "./__fixtures__/scenarios-priya-nair.json";
import { QuoteGroups } from "./QuoteGroups";

function renderGroups(view: ScenariosView) {
  return render(
    <QuoteGroups
      groups={view.groups}
      strategy={view.strategy ?? null}
      busy={false}
      compareIds={[]}
      onRecommend={vi.fn()}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      onToggleCompare={vi.fn()}
    />,
  );
}

describe("QuoteGroups", () => {
  it("AC1: Marcus Hale shows 4 quotes in 2 groups (DSCR 1.00 and his own DSCR)", () => {
    renderGroups(marcusFixture as ScenariosView);
    const groups = screen.getAllByTestId("quote-group");
    expect(groups).toHaveLength(2);
    expect(within(groups[0]).getByRole("heading")).toHaveTextContent("At DSCR 1.00");
    expect(within(groups[1]).getByRole("heading")).toHaveTextContent(/^At your DSCR \(0\.\d\d\)$/);
    expect(screen.getAllByRole("article")).toHaveLength(4);
    for (const group of groups) {
      expect(within(group).getByRole("article", { name: "Par quote" })).toBeInTheDocument();
      expect(within(group).getByRole("article", { name: "Buydown quote" })).toBeInTheDocument();
    }
    expect(screen.getAllByText("DSCR").length).toBeGreaterThan(0);
  });

  it("AC1: a same-bucket investment set shows one group with the note", () => {
    renderGroups(kathleenFixture as ScenariosView);
    expect(screen.getAllByTestId("quote-group")).toHaveLength(1);
    expect(screen.getByText("Your DSCR prices the same as 1.00")).toBeInTheDocument();
  });

  it("AC7: Priya Nair (primary) shows no DSCR, cashflow or prepayment text anywhere", () => {
    const { container } = renderGroups(priyaFixture as ScenariosView);
    expect(screen.getByRole("heading", { name: "At 20% down" })).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/DSCR|cashflow|prepay/i);
  });

  it("AC7: Daniel Ortiz's second group is at the 20% step that removes MI", () => {
    renderGroups(danielFixture as ScenariosView);
    const headings = screen.getAllByRole("heading").map((h) => h.textContent);
    expect(headings).toEqual(["At 5% down", "At 20% down"]);
  });

  it("shows credits as negative points in green and money from the API verbatim", () => {
    renderGroups(marcusFixture as ScenariosView);
    const par = within(screen.getAllByTestId("quote-group")[0]).getByRole("article", {
      name: "Par quote",
    });
    const quote = (marcusFixture as ScenariosView).groups[0].quotes[0];
    const points = within(par).getByText(/^-0\.375%/);
    expect(points).toHaveClass("text-status-success");
    expect(par).toHaveTextContent(
      `$${Number(quote.monthly_payment).toLocaleString("en-US", { minimumFractionDigits: 2 })}`,
    );
  });
});
