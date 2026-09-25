import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const getMock = vi.fn();

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock }),
}));

describe("Home page", () => {
  it("renders 'API reachable' when /health responds", async () => {
    getMock.mockResolvedValueOnce({
      data: { status: "ok", checks: { database: "ok", valkey: "ok", minio: "ok", temporal: "ok" } },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });

    const { default: Home } = await import("./page");
    render(<Home />);

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("API reachable"));
  });

  it("renders a degraded state listing the failing checks by name on a 503 response", async () => {
    // openapi-fetch resolves (does not reject) on a non-2xx response, and
    // treats a documented-only-as-200 endpoint's non-2xx body as `error`,
    // not `data` — the page must not treat this as "reachable".
    getMock.mockResolvedValueOnce({
      data: undefined,
      error: {
        status: "degraded",
        checks: {
          database: "ok",
          valkey: "error: connection refused",
          minio: "ok",
          temporal: "error: timeout",
        },
      },
      response: new Response(null, { status: 503 }),
    });

    const { default: Home } = await import("./page");
    render(<Home />);

    const status = await screen.findByRole("status");
    await waitFor(() => expect(status).toHaveTextContent("API degraded"));
    expect(status).toHaveTextContent("valkey");
    expect(status).toHaveTextContent("temporal");
    expect(status).not.toHaveTextContent("database");
    expect(status).not.toHaveTextContent("minio");
  });

  it("renders 'API unreachable' without throwing when the API call rejects", async () => {
    getMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    const { default: Home } = await import("./page");
    expect(() => render(<Home />)).not.toThrow();

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("API unreachable"));
  });
});
