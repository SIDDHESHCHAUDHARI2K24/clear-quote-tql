// AC1, AC3, AC7 (recalculating state) -- component tests against the
// Marcus Hale fixture (`__fixtures__/pricing-view-marcus-hale.json`,
// computed by the real `quote_engine`, see plan.md's fixtures note).
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, patchMock, postMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  patchMock: vi.fn(),
  postMock: vi.fn(),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, PATCH: patchMock, POST: postMock }),
}));

const refetchWorkspace = vi.fn();
vi.mock("../workspace", () => ({
  useWorkspace: () => ({
    applicationId: "11111111-1111-1111-1111-111111111111",
    refetch: refetchWorkspace,
  }),
}));

import marcusFixture from "./__fixtures__/pricing-view-marcus-hale.json";
import { PricingPanel } from "./PricingPanel";

describe("PricingPanel", () => {
  afterEach(() => {
    getMock.mockReset();
    patchMock.mockReset();
    postMock.mockReset();
    refetchWorkspace.mockReset();
  });

  it("AC1: shows loan amount $273,600.00, LTV 80.00% and P&I $1,913.05 for Marcus Hale", async () => {
    getMock.mockResolvedValueOnce({ data: marcusFixture, response: { status: 200 } });

    render(<PricingPanel />);

    await waitFor(() =>
      expect(screen.getByLabelText("Loan amount")).toHaveTextContent("$273,600.00"),
    );
    expect(screen.getByLabelText("LTV")).toHaveTextContent("80.00%");
    expect(screen.getByText("$1,913.05")).toBeInTheDocument();
  });

  it("AC3: overriding property tax shows 'LO override' and recomputes the total", async () => {
    getMock.mockResolvedValueOnce({ data: marcusFixture, response: { status: 200 } });
    render(<PricingPanel />);
    await waitFor(() =>
      expect(screen.getByLabelText("Loan amount")).toHaveTextContent("$273,600.00"),
    );

    const totalBefore = screen.getByText("Total monthly payment").closest("div")?.textContent;

    const overriddenFixture = {
      ...marcusFixture,
      has_stale_quotes: true,
      fields: marcusFixture.fields.map((f) =>
        f.field_key === "property_tax_annual_rate"
          ? {
              ...f,
              value: "0.03",
              source: "lo_override",
              overridden: true,
              original_value: "0.0225",
            }
          : f,
      ),
      breakdown: {
        ...marcusFixture.breakdown,
        monthly_tax: "855.00",
        total_monthly_payment: "2960.05",
      },
    };
    patchMock.mockResolvedValueOnce({
      data: { field_key: "property_tax_annual_rate" },
      response: { status: 200 },
    });
    getMock.mockResolvedValueOnce({ data: overriddenFixture, response: { status: 200 } });

    const taxInput = screen.getByLabelText("Property tax annual rate");
    await act(async () => {
      await userEvent.clear(taxInput);
      await userEvent.type(taxInput, "3.000");
      taxInput.blur();
    });

    await waitFor(() => expect(patchMock).toHaveBeenCalled());
    await waitFor(() => expect(screen.getAllByText(/LO override/i).length).toBeGreaterThan(0));
    await waitFor(() =>
      expect(screen.getByText("Quotes are out of date — Re-price")).toBeInTheDocument(),
    );
    expect(refetchWorkspace).toHaveBeenCalled();

    const totalAfter = screen.getByText("Total monthly payment").closest("div")?.textContent;
    expect(totalAfter).not.toBe(totalBefore);
  });

  it("shows the stale banner and a disabled Re-price button when has_stale_quotes is true", async () => {
    getMock.mockResolvedValueOnce({
      data: { ...marcusFixture, has_stale_quotes: true },
      response: { status: 200 },
    });
    render(<PricingPanel />);

    await waitFor(() =>
      expect(screen.getByText("Quotes are out of date — Re-price")).toBeInTheDocument(),
    );
    const button = screen.getByRole("button", { name: "Re-price" });
    expect(button).toBeDisabled();
  });

  it("AC7: shows a 'Recalculating…' indicator when a preview call takes over 300ms", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    getMock.mockResolvedValueOnce({ data: marcusFixture, response: { status: 200 } });
    render(<PricingPanel />);
    await waitFor(() =>
      expect(screen.getByLabelText("Loan amount")).toHaveTextContent("$273,600.00"),
    );

    let resolvePreview: (v: unknown) => void = () => {};
    postMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolvePreview = resolve;
        }),
    );

    const priceInput = screen.getByLabelText("Purchase price");
    await act(async () => {
      await userEvent.clear(priceInput);
      await userEvent.type(priceInput, "350000");
    });

    await act(async () => {
      vi.advanceTimersByTime(250); // debounce fires
    });
    await act(async () => {
      vi.advanceTimersByTime(350); // > 300ms in flight
    });
    expect(screen.getByText("Recalculating…")).toBeInTheDocument();

    await act(async () => {
      resolvePreview({
        data: { ...marcusFixture.breakdown, down_payment_pct: "0.2000" },
        response: { status: 200 },
      });
      await Promise.resolve();
    });

    vi.useRealTimers();
  });
});
