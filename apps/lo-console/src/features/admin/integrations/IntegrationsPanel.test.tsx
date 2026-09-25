import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, putMock, postMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  putMock: vi.fn(),
  postMock: vi.fn(),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, PUT: putMock, POST: postMock }),
}));

import { IntegrationsPanel } from "./IntegrationsPanel";
import type { AdapterStatus } from "./api";

function adapter(overrides: Partial<AdapterStatus> = {}): AdapterStatus {
  return {
    adapter: "pricing",
    provider: "Optimal Blue",
    last_call_at: new Date().toISOString(),
    last_latency_ms: 412,
    last_result: "ok",
    calls_last_hour: 3,
    force_failure: false,
    ...overrides,
  };
}

describe("IntegrationsPanel (AC4/AC5)", () => {
  afterEach(() => {
    getMock.mockReset();
    putMock.mockReset();
    postMock.mockReset();
  });

  it("lists every adapter with its last call, latency and result", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        adapters: [
          adapter(),
          adapter({
            adapter: "crm",
            provider: "Internal CRM log",
            last_result: "never_called",
            last_call_at: null,
            last_latency_ms: null,
          }),
        ],
      },
      response: { status: 200 },
    });

    render(<IntegrationsPanel />);

    expect(await screen.findByText("pricing")).toBeInTheDocument();
    expect(screen.getByText("Optimal Blue")).toBeInTheDocument();
    expect(screen.getByText("412 ms")).toBeInTheDocument();
    expect(screen.getByText("never_called")).toBeInTheDocument();
  });

  it("shows a banner when a failure is forced, and toggles it off", async () => {
    getMock.mockResolvedValueOnce({
      data: { adapters: [adapter({ force_failure: true })] },
      response: { status: 200 },
    });

    render(<IntegrationsPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/forced to fail/i);

    putMock.mockResolvedValueOnce({
      data: adapter({ force_failure: false }),
      error: undefined,
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("checkbox", { name: "Force pricing to fail" }));

    await waitFor(() =>
      expect(putMock).toHaveBeenCalledWith(
        "/api/v1/admin/integrations/{adapter}",
        expect.objectContaining({
          params: { path: { adapter: "pricing" } },
          body: { force_failure: false },
        }),
      ),
    );
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });

  // Code review finding: toggle() had no try/catch/finally, so a rejected
  // PUT (not just an `{error}` response) left the checkbox stuck disabled
  // and the optimistic update un-reverted.
  it("reverts the optimistic update and re-enables the checkbox when the PUT rejects", async () => {
    getMock.mockResolvedValueOnce({
      data: { adapters: [adapter({ force_failure: false })] },
      response: { status: 200 },
    });
    render(<IntegrationsPanel />);
    const checkbox = await screen.findByRole("checkbox", { name: "Force pricing to fail" });

    putMock.mockRejectedValueOnce(new Error("network drop"));
    const user = userEvent.setup();
    await user.click(checkbox);

    // The optimistic update reverts once the rejected promise is caught,
    // and the checkbox is usable again (not stuck disabled forever).
    await waitFor(() => expect(checkbox).not.toBeChecked());
    expect(checkbox).not.toBeDisabled();
  });

  // Review round 1, minor 6: a failed toggle used to revert silently --
  // nothing told the admin the PUT didn't take.
  it("shows a visible alert when the toggle PUT returns an error", async () => {
    getMock.mockResolvedValueOnce({
      data: { adapters: [adapter({ force_failure: false })] },
      response: { status: 200 },
    });
    render(<IntegrationsPanel />);
    const checkbox = await screen.findByRole("checkbox", { name: "Force pricing to fail" });

    putMock.mockResolvedValueOnce({ data: undefined, error: { detail: "Forbidden" } });
    const user = userEvent.setup();
    await user.click(checkbox);

    expect(await screen.findByText("Forbidden")).toBeInTheDocument();
    await waitFor(() => expect(checkbox).not.toBeChecked());
  });

  // Review round 1, minor 6: pending state is now a `Set`, so toggling one
  // adapter while another adapter's PUT is still in flight doesn't disable
  // (or fail to disable) the wrong row.
  it("tracks pending adapters independently", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        adapters: [adapter({ adapter: "pricing" }), adapter({ adapter: "credit" })],
      },
      response: { status: 200 },
    });
    render(<IntegrationsPanel />);
    const pricingCheckbox = await screen.findByRole("checkbox", { name: "Force pricing to fail" });
    const creditCheckbox = screen.getByRole("checkbox", { name: "Force credit to fail" });

    let resolvePut: (value: { data: AdapterStatus; error: undefined }) => void = () => {};
    putMock.mockReturnValueOnce(
      new Promise((resolve) => {
        resolvePut = resolve;
      }),
    );
    const user = userEvent.setup();
    await user.click(pricingCheckbox);

    // The in-flight adapter is disabled; the other one is untouched.
    await waitFor(() => expect(pricingCheckbox).toBeDisabled());
    expect(creditCheckbox).not.toBeDisabled();

    resolvePut({ data: adapter({ adapter: "pricing", force_failure: true }), error: undefined });
    await waitFor(() => expect(pricingCheckbox).not.toBeDisabled());
  });

  // CQ-030 has merged: the "Run stale check now" button is no longer
  // hidden behind STALE_CHECK_JOB_AVAILABLE.
  it("runs the stale check and shows the returned counts", async () => {
    getMock.mockResolvedValueOnce({
      data: { adapters: [adapter()] },
      response: { status: 200 },
    });
    render(<IntegrationsPanel />);
    await screen.findByText("pricing");

    postMock.mockResolvedValueOnce({
      data: {
        ran_at: new Date().toISOString(),
        quotes_marked_stale: 3,
        versions_expired: 2,
        applications_marked_stale: 1,
        application_ids: ["11111111-1111-1111-1111-111111111111"],
      },
      error: undefined,
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Run stale check now" }));

    await waitFor(() => expect(postMock).toHaveBeenCalledWith("/api/v1/admin/jobs/stale-check"));
    expect(
      await screen.findByText("Marked 3 quotes stale, expired 2 versions, flagged 1 application."),
    ).toBeInTheDocument();
  });

  // Review round 1, minor 6: an uncaught rejection from `fetchIntegrations`
  // (a network drop, not just an `{error}` response) used to leave the
  // panel stuck on "Loading integrations…" forever.
  it("shows an error with a Retry action when loading rejects, and Retry re-fetches", async () => {
    getMock.mockRejectedValueOnce(new Error("network drop"));
    render(<IntegrationsPanel />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't load/i);

    getMock.mockResolvedValueOnce({
      data: { adapters: [adapter()] },
      response: { status: 200 },
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("pricing")).toBeInTheDocument();
  });

  it("shows an error if the stale check request fails", async () => {
    getMock.mockResolvedValueOnce({
      data: { adapters: [adapter()] },
      response: { status: 200 },
    });
    render(<IntegrationsPanel />);
    await screen.findByText("pricing");

    postMock.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "Forbidden" },
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Run stale check now" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Forbidden");
  });
});
