import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

// `vi.hoisted`: the api-client mock factory runs when `lib/api-client` is
// first imported (hoisted above plain `const`s).
const { getMock, postMock, replaceMock, nav } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
  replaceMock: vi.fn(),
  nav: { pathname: "/" },
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: postMock }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  usePathname: () => nav.pathname,
}));

import { BorrowerSessionProvider, loginUrlFor, PortalShell, useBorrowerSession } from "./index";

const BORROWER_ME = {
  account_id: "11111111-1111-1111-1111-111111111111",
  email: "casey@clearquote.test",
  client_id: "22222222-2222-2222-2222-222222222222",
  full_name: "Casey Morgan",
  first_name: "Casey",
  latest_application: null,
};

function renderShell() {
  return render(
    <BorrowerSessionProvider>
      <PortalShell>
        <p>Page body</p>
      </PortalShell>
    </BorrowerSessionProvider>,
  );
}

afterEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  postMock.mockResolvedValue({ data: undefined, error: undefined });
  replaceMock.mockReset();
  nav.pathname = "/";
});

describe("PortalShell", () => {
  it("renders the logo, Home and Support nav, and the page", async () => {
    getMock.mockResolvedValueOnce({ data: BORROWER_ME, error: undefined });
    renderShell();

    expect(await screen.findByRole("link", { name: /TQL/ })).toHaveAttribute("href", "/");
    const nav = screen.getByRole("navigation", { name: "Main" });
    const links = Array.from(nav.querySelectorAll("a")).map((a) => [
      a.textContent,
      a.getAttribute("href"),
    ]);
    expect(links).toEqual([
      ["Home", "/"],
      ["Support", "/support"],
    ]);
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Page body")).toBeInTheDocument();
  });

  it("shows the core disclosures in the footer", async () => {
    getMock.mockResolvedValueOnce({ data: BORROWER_ME, error: undefined });
    renderShell();
    const footer = await screen.findByRole("contentinfo");
    expect(footer).toHaveTextContent("NMLS #");
    expect(footer).toHaveTextContent("Equal Housing Lender");
    expect(footer).toHaveTextContent("Not a commitment to lend");
  });

  it("signs out from the account menu", async () => {
    getMock.mockResolvedValueOnce({ data: BORROWER_ME, error: undefined });
    renderShell();
    await userEvent.click(await screen.findByRole("button", { name: /Account menu for Casey/ }));
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith("/api/v1/auth/borrower/logout"));
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });
});

describe("BorrowerSessionProvider", () => {
  function Probe() {
    const { me } = useBorrowerSession();
    return <p data-testid="probe">{me.full_name}</p>;
  }

  it("loads /me once and exposes it", async () => {
    getMock.mockResolvedValueOnce({ data: BORROWER_ME, error: undefined });
    render(
      <BorrowerSessionProvider>
        <Probe />
      </BorrowerSessionProvider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Checking session…");
    expect(await screen.findByTestId("probe")).toHaveTextContent("Casey Morgan");
    expect(getMock).toHaveBeenCalledTimes(1);
    expect(getMock).toHaveBeenCalledWith("/api/v1/auth/borrower/me");
  });

  it("clears the stale cookie and redirects to /login?next=<path> on a 401", async () => {
    nav.pathname = "/support";
    getMock.mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "AUTHENTICATION_ERROR", message: "Not authenticated" } },
      response: { status: 401 },
    });
    render(
      <BorrowerSessionProvider>
        <Probe />
      </BorrowerSessionProvider>,
    );
    await waitFor(() => expect(postMock).toHaveBeenCalledWith("/api/v1/auth/borrower/logout"));
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login?next=%2Fsupport"));
    expect(screen.queryByTestId("probe")).not.toBeInTheDocument();
  });

  it("shows a retry state (no logout, no redirect) on a non-401 error", async () => {
    getMock.mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "INTERNAL_ERROR", message: "Boom" } },
      response: { status: 500 },
    });
    render(
      <BorrowerSessionProvider>
        <Probe />
      </BorrowerSessionProvider>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/Can.t reach the server/);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(postMock).not.toHaveBeenCalled();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("shows a retry state (no logout, no redirect) when /me rejects (network error)", async () => {
    getMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(
      <BorrowerSessionProvider>
        <Probe />
      </BorrowerSessionProvider>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/Can.t reach the server/);
    expect(postMock).not.toHaveBeenCalled();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("retries the session check from the retry state and recovers", async () => {
    getMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    getMock.mockResolvedValueOnce({ data: BORROWER_ME, error: undefined });
    render(
      <BorrowerSessionProvider>
        <Probe />
      </BorrowerSessionProvider>,
    );
    const retry = await screen.findByRole("button", { name: "Retry" });

    fireEvent.click(retry);

    expect(await screen.findByTestId("probe")).toHaveTextContent("Casey Morgan");
    expect(getMock).toHaveBeenCalledTimes(2);
  });

  it.each([
    ["/", "/login"],
    ["/apply", "/login?next=%2Fapply"],
    ["/tasks/credit-check/abc", "/login?next=%2Ftasks%2Fcredit-check%2Fabc"],
    ["//evil.com", "/login"],
  ])("loginUrlFor(%s) -> %s", (path, expected) => {
    expect(loginUrlFor(path)).toBe(expected);
  });
});
