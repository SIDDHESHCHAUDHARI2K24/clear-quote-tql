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

  it("renders 'API unreachable' without throwing when the API call rejects", async () => {
    getMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    const { default: Home } = await import("./page");
    expect(() => render(<Home />)).not.toThrow();

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("API unreachable"));
  });
});
