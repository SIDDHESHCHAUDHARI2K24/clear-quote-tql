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

const STAFF_USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "lo@clearquote.test",
  full_name: "Jamie Rivera",
  role: "lo" as const,
  nmls: null,
  title: null,
  phone: null,
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

  it("shows the signed-in user's name and role label once /me resolves", async () => {
    getMock.mockResolvedValueOnce({ data: STAFF_USER, error: undefined });

    const { default: Home } = await import("./page");
    render(<Home />);

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "Signed in as Jamie Rivera (Loan Officer)",
      ),
    );
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("maps the manager and admin roles to their display labels", async () => {
    getMock.mockResolvedValueOnce({
      data: { ...STAFF_USER, full_name: "Casey Admin", role: "admin" },
      error: undefined,
    });

    const { default: Home } = await import("./page");
    render(<Home />);

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Signed in as Casey Admin (Admin)"),
    );
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
    await waitFor(() => expect(postMock).toHaveBeenCalledWith("/api/v1/auth/staff/logout"));
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });

  it("redirects to /login without throwing when the /me call rejects", async () => {
    getMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    const { default: Home } = await import("./page");
    expect(() => render(<Home />)).not.toThrow();

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });

  it("calls the logout endpoint and redirects to /login on Logout", async () => {
    getMock.mockResolvedValueOnce({ data: STAFF_USER, error: undefined });
    postMock.mockResolvedValueOnce({ data: undefined, error: undefined });
    const user = userEvent.setup();

    const { default: Home } = await import("./page");
    render(<Home />);

    const logoutButton = await screen.findByRole("button", { name: "Logout" });
    await user.click(logoutButton);

    await waitFor(() => expect(postMock).toHaveBeenCalledWith("/api/v1/auth/staff/logout"));
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });

  it("still redirects to /login on Logout even when the logout request fails", async () => {
    getMock.mockResolvedValueOnce({ data: STAFF_USER, error: undefined });
    postMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const user = userEvent.setup();

    const { default: Home } = await import("./page");
    render(<Home />);

    const logoutButton = await screen.findByRole("button", { name: "Logout" });
    await user.click(logoutButton);

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });
});
