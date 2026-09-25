import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HeroNumbers } from "./HeroNumbers";
import marcusHale from "./__fixtures__/marcus_hale.json";
import priyaNair from "./__fixtures__/priya_nair.json";
import type { ReportViewModelData } from "./types";

const marcus = marcusHale as ReportViewModelData;
const priya = priyaNair as ReportViewModelData;

describe("HeroNumbers", () => {
  it("AC1: Marcus Hale's par option shows the pinned tax-savings and red STR cashflow", () => {
    const par = marcus.options.find((o) => o.recommended)!;
    render(<HeroNumbers option={par} strategy={marcus.strategy} />);

    expect(screen.getByText("$24,276")).toBeInTheDocument(); // year1_tax_savings "24275.78"
    expect(screen.getByText("≈ $2,023/mo")).toBeInTheDocument();
    expect(screen.getByText(/Estimated monthly cashflow \(STR\)/i)).toBeInTheDocument();

    const cashflowLabel = screen.getByText(/Estimated monthly cashflow \(STR\)/i);
    const cashflowTile = cashflowLabel.closest("div.rounded-lg")!;
    // `.num` (not `.text-3xl`) -- CQ-022 AC7 shrinks the value text at the
    // mobile breakpoint (`text-2xl sm:text-3xl`), so `.text-3xl` alone no
    // longer matches; `.num` stays on the value element at every size.
    const valueEl = cashflowTile.querySelector(".num.font-semibold")!;
    expect(valueEl.className).toContain("text-status-danger");
  });

  it("AC2: Priya Nair's (primary) hero renders exactly 3 tiles and no investment content", () => {
    const option = priya.options[0];
    const { container } = render(<HeroNumbers option={option} strategy={priya.strategy} />);

    const tiles = container.querySelectorAll('[data-testid="hero-numbers"] > div');
    expect(tiles).toHaveLength(3);

    expect(screen.queryByText(/DSCR/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/cashflow/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/tax savings/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Loan amount/i)).toBeInTheDocument();
  });
});
