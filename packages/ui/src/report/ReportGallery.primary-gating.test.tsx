// AC2's "DOM assertion over the whole gallery page" -- rendering the full
// `ReportPage` composition (what both apps' `/gallery/report` pages mount)
// for the primary fixture and asserting no investment-only content leaks in
// anywhere, not just within one component in isolation.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { formatMoneyPrecise } from "./format";
import { ReportPage } from "./ReportPage";
import danielOrtiz from "./__fixtures__/daniel_ortiz.json";
import kathleenMcreynolds from "./__fixtures__/kathleen_mcreynolds.json";
import marcusHale from "./__fixtures__/marcus_hale.json";
import marcusHaleExpired from "./__fixtures__/marcus_hale_expired.json";
import priyaNair from "./__fixtures__/priya_nair.json";
import priyaNairSuperseded from "./__fixtures__/priya_nair_superseded.json";
import type { ReportViewModelData } from "./types";

const priya = priyaNair as ReportViewModelData;
const daniel = danielOrtiz as ReportViewModelData;
const kathleen = kathleenMcreynolds as ReportViewModelData;
const marcus = marcusHale as ReportViewModelData;
const marcusExpired = marcusHaleExpired as ReportViewModelData;
const priyaSuperseded = priyaNairSuperseded as ReportViewModelData;

const FORBIDDEN_ON_PRIMARY = [
  /DSCR/i,
  /cashflow/i,
  /cap rate/i,
  /cost segregation/i,
  /prepayment penalty/i,
  /tax savings/i,
  /tax advice/i,
  /rental income/i,
];

describe("Primary loans never show investment content (AC2, system-design.md principle 4)", () => {
  it("Priya Nair (primary, 20% down): 3 hero tiles, nothing investment-only anywhere on the page", () => {
    const { container } = render(<ReportPage viewModel={priya} />);

    const heroTiles = container.querySelectorAll('[data-testid="hero-numbers"] > div');
    expect(heroTiles).toHaveLength(3);

    // Collapsible.tsx (CQ-022 AC6/print) mounts each section's content
    // unconditionally and only CSS-hides it (Tailwind's `.hidden` class)
    // while collapsed -- a DOM-presence check alone can no longer tell
    // collapsed from expanded, since both mount the same nodes. jsdom
    // doesn't apply the compiled Tailwind stylesheet (jest-dom's
    // `toBeVisible()` would see the class-hidden element as visible), so
    // this asserts the actual mechanism our component controls -- the
    // `.hidden` class itself -- toggling off on expand.
    const breakdownToggle = screen.getByRole("button", { name: /full breakdown/i });
    const breakdownContent = breakdownToggle.nextElementSibling as HTMLElement;
    expect(breakdownContent.classList.contains("hidden")).toBe(true);

    // Expand both collapsibles so their (already-mounted) content becomes
    // visible, then scan the whole page for anything investment-only.
    for (const button of screen.getAllByRole("button", { name: /see/i })) {
      fireEvent.click(button);
    }
    expect(breakdownContent.classList.contains("hidden")).toBe(false);

    for (const pattern of FORBIDDEN_ON_PRIMARY) {
      expect(container.textContent).not.toMatch(pattern);
    }
  });

  it("Daniel Ortiz (primary with MI): still no investment content, MI shows in the breakdown", () => {
    const { container } = render(<ReportPage viewModel={daniel} />);

    for (const button of screen.getAllByRole("button", { name: /see/i })) {
      fireEvent.click(button);
    }

    for (const pattern of FORBIDDEN_ON_PRIMARY) {
      expect(container.textContent).not.toMatch(pattern);
    }
    expect(screen.getByText("Mortgage insurance")).toBeInTheDocument();
  });
});

describe("AC3: Kathleen McReynolds (LTR, TBD property)", () => {
  it("shows the TBD label and LTR, never STR", () => {
    const { container } = render(<ReportPage viewModel={kathleen} />);

    expect(screen.getByText("Property to be determined")).toBeInTheDocument();
    expect(container.textContent).toMatch(/LTR/);
    expect(container.textContent).not.toMatch(/\bSTR\b/);
  });
});

describe("AC4: switching options updates every dependent number, unchanged values stay put", () => {
  it("Marcus Hale: clicking Buydown changes hero, breakdown and cashflow to that option's own fixture values", () => {
    render(<ReportPage viewModel={marcus} />);
    const [par, buydown] = marcus.options;
    expect(par.hero.monthly_payment).not.toBe(buydown.hero.monthly_payment);
    expect(par.breakdown.payment_lines[0].amount).not.toBe(
      buydown.breakdown.payment_lines[0].amount,
    );

    // Expand "See the full breakdown" so the breakdown/cashflow tables are
    // in the DOM to assert on.
    fireEvent.click(screen.getByRole("button", { name: /full breakdown/i }));

    const piLabel = par.breakdown.payment_lines[0].label; // "Principal & interest"
    const piRow = () => screen.getByText(piLabel).closest("div")!;
    expect(piRow().textContent).toContain(
      formatMoneyPrecise(par.breakdown.payment_lines[0].amount),
    );

    const buydownPill = screen.getByRole("radio", { name: new RegExp(buydown.label, "i") });
    fireEvent.click(buydownPill);

    // No recomputation in the frontend: the new value is exactly the
    // buydown fixture's own (already engine-computed) amount.
    expect(piRow().textContent).toContain(
      formatMoneyPrecise(buydown.breakdown.payment_lines[0].amount),
    );
    expect(piRow().textContent).not.toContain(
      formatMoneyPrecise(par.breakdown.payment_lines[0].amount),
    );
  });
});

describe("Expired and superseded banners", () => {
  it("renders the expired banner only when header.expired is true", () => {
    render(<ReportPage viewModel={marcusExpired} />);
    expect(screen.getByText("These numbers have expired.")).toBeInTheDocument();
  });

  it("does not render the expired banner for a non-expired fixture", () => {
    render(<ReportPage viewModel={marcus} />);
    expect(screen.queryByText("These numbers have expired.")).not.toBeInTheDocument();
  });

  it("renders the superseded banner only when header.superseded is true", () => {
    render(<ReportPage viewModel={priyaSuperseded} />);
    expect(screen.getByText(/newer version of this report/i)).toBeInTheDocument();
  });
});
