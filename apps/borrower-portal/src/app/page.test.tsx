import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
// Default resolved value covers the best-effort logout call page.tsx fires
// when /me 401s; individual tests override with mockResolvedValueOnce for
// the explicit "click Logout" assertions.
const postMock = vi.fn().mockResolvedValue({ data: undefined, error: undefined });
const replaceMock = vi.fn();

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: postMock }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

const BORROWER_ME = {
  account_id: "11111111-1111-1111-1111-111111111111",
  email: "borrower@clearquote.test",
  client_id: "22222222-2222-2222-2222-222222222222",
  full_name: "Casey Morgan",
  first_name: "Casey",
  latest_application: null as { id: string; status: string } | null,
};

describe("Home page", () => {
  afterEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    // Default: any call not given its own mockResolvedValueOnce (e.g. the
    // best-effort logout the page fires when /me 401s) resolves cleanly
    // instead of returning undefined, which would throw on `.catch(...)`.
    postMock.mockResolvedValue({ data: undefined, error: undefined });
    replaceMock.mockReset();
  });

  it("shows the signed-in borrower's first name once /me resolves", async () => {
    getMock.mockResolvedValueOnce({ data: BORROWER_ME, error: undefined });

    const { default: Home } = await import("./page");
    render(<Home />);

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Hi Casey"));
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("shows 'No application yet' when there is no latest application", async () => {
    getMock.mockResolvedValueOnce({ data: BORROWER_ME, error: undefined });

    const { default: Home } = await import("./page");
    render(<Home />);

    await waitFor(() => expect(screen.getByText("No application yet")).toBeInTheDocument());
  });

  it("shows the human status label for the latest application", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        ...BORROWER_ME,
        latest_application: { id: "33333333-3333-3333-3333-333333333333", status: "priced" },
      },
      error: undefined,
    });

    const { default: Home } = await import("./page");
    render(<Home />);

    await waitFor(() => expect(screen.getByText("Pre-approved")).toBeInTheDocument());
  });

  it("redirects to /login when /me returns 401 (data undefined), clearing the stale cookie first", async () => {
    getMock.mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "AUTHENTICATION_ERROR", message: "Not authenticated" } },
    });

    const { default: Home } = await import("./page");
    render(<Home />);

    // A present-but-invalid cookie must be cleared via logout before the
    // redirect, or middleware (which only checks presence) would bounce
    // this /login navigation straight back to /.
    await waitFor(() => expect(postMock).toHaveBeenCalledWith("/api/v1/auth/borrower/logout"));
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });

  it("redirects to /login without throwing when the /me call rejects", async () => {
    getMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    const { default: Home } = await import("./page");
    expect(() => render(<Home />)).not.toThrow();

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });

  it("calls the logout endpoint and redirects to /login on Logout", async () => {
    getMock.mockResolvedValueOnce({ data: BORROWER_ME, error: undefined });
    postMock.mockResolvedValueOnce({ data: undefined, error: undefined });
    const user = userEvent.setup();

    const { default: Home } = await import("./page");
    render(<Home />);

    const logoutButton = await screen.findByRole("button", { name: "Logout" });
    await user.click(logoutButton);

    await waitFor(() => expect(postMock).toHaveBeenCalledWith("/api/v1/auth/borrower/logout"));
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });

  it("still redirects to /login on Logout even when the logout request fails", async () => {
    getMock.mockResolvedValueOnce({ data: BORROWER_ME, error: undefined });
    postMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const user = userEvent.setup();

    const { default: Home } = await import("./page");
    render(<Home />);

    const logoutButton = await screen.findByRole("button", { name: "Logout" });
    await user.click(logoutButton);

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });
});
