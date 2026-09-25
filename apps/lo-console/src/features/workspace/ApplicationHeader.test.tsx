import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, patchMock } = vi.hoisted(() => ({ getMock: vi.fn(), patchMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, PATCH: patchMock }),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/applications/11111111-1111-1111-1111-111111111111/pricing",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

import { WorkspaceHeader } from "./WorkspaceHeader";
import { WorkspaceProvider } from "./WorkspaceProvider";
import { makeSummary } from "./test-fixtures";

const APPLICATION_ID = "11111111-1111-1111-1111-111111111111";

// spec.md AC2/AC3: PPP hidden for primary loans, shown for investment; note
// rate reads "—" until a quote is recommended, then the recommended
// quote's rate.
describe("WorkspaceHeader (AC2/AC3)", () => {
  afterEach(() => {
    getMock.mockReset();
    patchMock.mockReset();
  });

  it("Priya Nair (primary): no PPP field, note rate shows — with a tooltip", async () => {
    getMock.mockResolvedValueOnce({
      data: makeSummary({ occupancy: "primary", strategy: null, note_rate: null }),
      response: { status: 200 },
    });

    render(
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <WorkspaceHeader />
      </WorkspaceProvider>,
    );

    await waitFor(() => expect(screen.getByText("Priya Nair")).toBeInTheDocument());
    expect(screen.queryByText("PPP")).not.toBeInTheDocument();
    const noteRate = screen.getByText("—", { selector: "dd" });
    expect(noteRate.closest("[title]")).toHaveAttribute("title", "Set after pricing");
  });

  it("Marcus Hale (STR): shows PPP and the recommended quote's rate", async () => {
    getMock.mockResolvedValueOnce({
      data: makeSummary({
        client_name: "Marcus Hale",
        occupancy: "investment",
        strategy: "str",
        ppp_years: 5,
        note_rate: "7.500",
      }),
      response: { status: 200 },
    });

    render(
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <WorkspaceHeader />
      </WorkspaceProvider>,
    );

    await waitFor(() => expect(screen.getByText("Marcus Hale")).toBeInTheDocument());
    expect(screen.getByText("PPP")).toBeInTheDocument();
    expect(screen.getByText("5y PPP")).toBeInTheDocument();
    expect(screen.getByText("7.500%")).toBeInTheDocument();
  });

  it("renders header numbers in spec order: purchasing power, down payment, PPP, note rate, strategy, program, location", async () => {
    getMock.mockResolvedValueOnce({
      data: makeSummary({
        occupancy: "investment",
        strategy: "ltr",
        ppp_years: 5,
        note_rate: "7.125",
      }),
      response: { status: 200 },
    });

    render(
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <WorkspaceHeader />
      </WorkspaceProvider>,
    );

    await waitFor(() => expect(screen.getByText("Purchasing power")).toBeInTheDocument());
    const labels = screen.getAllByRole("term").map((el) => el.textContent);
    expect(labels).toEqual([
      "Purchasing power",
      "Down payment",
      "PPP",
      "Note rate",
      "Strategy",
      "Program",
      "Location",
    ]);
  });
});
