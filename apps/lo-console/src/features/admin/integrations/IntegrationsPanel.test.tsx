import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, putMock } = vi.hoisted(() => ({ getMock: vi.fn(), putMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, PUT: putMock }),
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
});
