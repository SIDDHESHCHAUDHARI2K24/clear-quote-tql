import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, patchMock } = vi.hoisted(() => ({ getMock: vi.fn(), patchMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, PATCH: patchMock }),
}));

import { StatusActionsMenu } from "./StatusActionsMenu";
import { makeSummary } from "./test-fixtures";
import { WorkspaceProvider } from "./WorkspaceProvider";

const APPLICATION_ID = "11111111-1111-1111-1111-111111111111";

async function renderReady(overrides = {}) {
  getMock.mockResolvedValueOnce({ data: makeSummary(overrides), response: { status: 200 } });
  render(
    <WorkspaceProvider applicationId={APPLICATION_ID}>
      <StatusActionsMenu />
    </WorkspaceProvider>,
  );
  await waitFor(() => expect(getMock).toHaveBeenCalledTimes(1));
}

// spec.md AC6: withdrawing sets status Withdrawn via a confirm dialog with
// a reason field; the menu is hidden once status is already terminal.
describe("StatusActionsMenu (AC6)", () => {
  afterEach(() => {
    getMock.mockReset();
    patchMock.mockReset();
  });

  it("hides the menu once the application is already terminal", async () => {
    await renderReady({ status: "withdrawn" });
    expect(screen.queryByRole("button", { name: "Actions" })).not.toBeInTheDocument();
  });

  it("withdraws the application after confirming, with the reason", async () => {
    const user = userEvent.setup();
    await renderReady({ status: "priced" });
    patchMock.mockResolvedValueOnce({
      data: makeSummary({ status: "withdrawn" }),
      error: undefined,
    });
    // The refetch after a successful PATCH.
    getMock.mockResolvedValueOnce({
      data: makeSummary({ status: "withdrawn" }),
      response: { status: 200 },
    });

    await user.click(screen.getByRole("button", { name: "Actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Withdraw application" }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Reason/), "Borrower backed out");
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(patchMock).toHaveBeenCalledWith(
        "/api/v1/applications/{application_id}/status",
        expect.objectContaining({
          params: { path: { application_id: APPLICATION_ID } },
          body: { status: "withdrawn", reason: "Borrower backed out" },
        }),
      ),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows the API's error message and keeps the dialog open on failure", async () => {
    const user = userEvent.setup();
    await renderReady({ status: "priced" });
    patchMock.mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "CONFLICT", message: "Application is already withdrawn." } },
    });

    await user.click(screen.getByRole("button", { name: "Actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Close application" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Application is already withdrawn.",
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
