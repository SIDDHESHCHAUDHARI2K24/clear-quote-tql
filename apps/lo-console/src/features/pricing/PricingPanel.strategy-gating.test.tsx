// AC4, AC5: strategy gating over 4 persona fixtures (+ Asheville for the
// green DSCR case) -- primary never shows the investment block or PPP;
// investment shows exactly one of LTR/STR; MI shows only when primary and
// LTV > 80%; DSCR is coloured per spec.md's thresholds.
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, PATCH: vi.fn(), POST: vi.fn() }),
}));

vi.mock("../workspace", () => ({
  useWorkspace: () => ({
    applicationId: "00000000-0000-0000-0000-000000000000",
    refetch: vi.fn(),
  }),
}));

import asheville from "./__fixtures__/pricing-view-asheville-holdings.json";
import daniel from "./__fixtures__/pricing-view-daniel-ortiz.json";
import kathleen from "./__fixtures__/pricing-view-kathleen-mcreynolds.json";
import marcus from "./__fixtures__/pricing-view-marcus-hale.json";
import priya from "./__fixtures__/pricing-view-priya-nair.json";
import { PricingPanel } from "./PricingPanel";

describe("PricingPanel strategy gating (AC4)", () => {
  afterEach(() => getMock.mockReset());

  it("Priya Nair (primary): no investment block, no PPP field", async () => {
    getMock.mockResolvedValueOnce({ data: priya, response: { status: 200 } });
    render(<PricingPanel />);
    await waitFor(() => expect(screen.getByLabelText("Loan amount")).toBeInTheDocument());

    expect(screen.queryByText("Long-term rental")).not.toBeInTheDocument();
    expect(screen.queryByText("Short-term rental")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("DSCR")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Prepayment penalty")).not.toBeInTheDocument();
  });

  it("Daniel Ortiz (primary, 5% down): shows an MI line", async () => {
    getMock.mockResolvedValueOnce({ data: daniel, response: { status: 200 } });
    render(<PricingPanel />);
    await waitFor(() => expect(screen.getByLabelText("Loan amount")).toBeInTheDocument());

    expect(screen.getByText("MI")).toBeInTheDocument();
    expect(screen.queryByText("Long-term rental")).not.toBeInTheDocument();
    expect(screen.queryByText("Short-term rental")).not.toBeInTheDocument();
  });

  it("Marcus Hale: STR block only, never LTR", async () => {
    getMock.mockResolvedValueOnce({ data: marcus, response: { status: 200 } });
    render(<PricingPanel />);
    await waitFor(() => expect(screen.getByLabelText("Loan amount")).toBeInTheDocument());

    expect(screen.getByText("Short-term rental")).toBeInTheDocument();
    expect(screen.queryByText("Long-term rental")).not.toBeInTheDocument();
    expect(screen.queryByText("MI")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Prepayment penalty")).toBeInTheDocument();
  });

  it("Kathleen McReynolds: LTR block only, never STR", async () => {
    getMock.mockResolvedValueOnce({ data: kathleen, response: { status: 200 } });
    render(<PricingPanel />);
    await waitFor(() => expect(screen.getByLabelText("Loan amount")).toBeInTheDocument());

    expect(screen.getByText("Long-term rental")).toBeInTheDocument();
    expect(screen.queryByText("Short-term rental")).not.toBeInTheDocument();
  });
});

describe("PricingPanel DSCR colouring (AC5)", () => {
  afterEach(() => getMock.mockReset());

  it("Marcus Hale's DSCR (0.90) renders amber", async () => {
    getMock.mockResolvedValueOnce({ data: marcus, response: { status: 200 } });
    render(<PricingPanel />);
    await waitFor(() => expect(screen.getByLabelText("DSCR")).toHaveTextContent("0.90"));
    expect(screen.getByLabelText("DSCR").className).toContain("text-status-warning");
  });

  it("Asheville Holdings' DSCR (>= 1.25) renders green", async () => {
    getMock.mockResolvedValueOnce({ data: asheville, response: { status: 200 } });
    render(<PricingPanel />);
    await waitFor(() => expect(screen.getByLabelText("DSCR")).toBeInTheDocument());
    const dscrText = screen.getByLabelText("DSCR").textContent ?? "";
    expect(Number(dscrText)).toBeGreaterThanOrEqual(1.25);
    expect(screen.getByLabelText("DSCR").className).toContain("text-status-success");
  });

  it("Kathleen McReynolds' DSCR (1.00-1.24) renders neutral", async () => {
    getMock.mockResolvedValueOnce({ data: kathleen, response: { status: 200 } });
    render(<PricingPanel />);
    await waitFor(() => expect(screen.getByLabelText("DSCR")).toBeInTheDocument());
    const dscrText = screen.getByLabelText("DSCR").textContent ?? "";
    const value = Number(dscrText);
    expect(value).toBeGreaterThanOrEqual(1.0);
    expect(value).toBeLessThan(1.25);
    expect(screen.getByLabelText("DSCR").className).toContain("text-navy-900");
  });
});
