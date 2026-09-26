import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

// `vi.hoisted`: the api-client mock factory runs when `lib/api-client`
// is first imported (hoisted above plain `const`s).
const { getMock, postMock, replaceMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
  replaceMock: vi.fn(),
}));
let pathname = "/";

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: postMock }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  usePathname: () => pathname,
}));

import { AdminGuard, StaffSessionProvider, StaffShell } from "./index";

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "lo@clearquote.test",
  full_name: "Jordan Lee",
  role: "lo" as const,
  nmls: null,
  title: null,
  phone: null,
};

function renderShell(role: "lo" | "manager" | "admin", children = <p>Page body</p>) {
  getMock.mockResolvedValueOnce({ data: { ...USER, role }, error: undefined });
  return render(
    <StaffSessionProvider>
      <StaffShell>{children}</StaffShell>
    </StaffSessionProvider>,
  );
}

async function openMenu() {
  await userEvent.click(await screen.findByRole("button", { name: /Jordan Lee/ }));
}

describe("StaffShell", () => {
  afterEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    postMock.mockResolvedValue({ data: undefined, error: undefined });
    replaceMock.mockReset();
    pathname = "/";
  });

  it("renders the four nav links with their routes", async () => {
    renderShell("lo");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    const links = Array.from(nav.querySelectorAll("a")).map((a) => [
      a.textContent,
      a.getAttribute("href"),
    ]);
    expect(links).toEqual([
      ["Dashboard", "/"],
      ["Clients", "/clients"],
      ["Applications", "/applications"],
      ["Outbox", "/outbox"],
    ]);
    expect(screen.getByText("Page body")).toBeInTheDocument();
  });

  it("marks the current section, including nested workspace routes", async () => {
    pathname = "/applications/abc/pricing";
    renderShell("lo");
    expect(await screen.findByRole("link", { name: "Applications" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
  });

  it("shows name, role and admin links in the user menu for an Admin", async () => {
    renderShell("admin");
    await openMenu();
    expect(screen.getByTestId("user-menu-identity")).toHaveTextContent(
      "Signed in as Jordan Lee (Admin)",
    );
    expect(screen.getByRole("link", { name: "Integrations" })).toHaveAttribute(
      "href",
      "/admin/integrations",
    );
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute(
      "href",
      "/admin/settings",
    );
  });

  it.each([
    ["lo", "Loan Officer"],
    ["manager", "Manager"],
  ] as const)("hides the admin links for a %s", async (role, label) => {
    renderShell(role);
    await openMenu();
    expect(screen.getByTestId("user-menu-identity")).toHaveTextContent(`(${label})`);
    expect(screen.queryByRole("link", { name: "Integrations" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
  });

  it("signs out through the menu", async () => {
    renderShell("lo");
    await openMenu();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith("/api/v1/auth/staff/logout"));
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });

  it("still signs out when the logout request fails", async () => {
    renderShell("lo");
    await openMenu();
    postMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });

  it("closes the menu on Escape and returns focus to its button", async () => {
    const user = userEvent.setup();
    renderShell("admin");
    const button = await screen.findByRole("button", { name: /Jordan Lee/ });
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(document.activeElement).toBe(button);
  });
});

describe("AdminGuard", () => {
  afterEach(() => {
    getMock.mockReset();
  });

  it("renders admin pages for an Admin", async () => {
    renderShell("admin", <AdminGuard>Admin page</AdminGuard>);
    expect(await screen.findByText("Admin page")).toBeInTheDocument();
  });

  it.each(["lo", "manager"] as const)("shows not-authorized to a %s", async (role) => {
    renderShell(role, <AdminGuard>Admin page</AdminGuard>);
    expect(await screen.findByRole("heading", { name: "Not authorized" })).toBeInTheDocument();
    expect(screen.queryByText("Admin page")).not.toBeInTheDocument();
  });
});
