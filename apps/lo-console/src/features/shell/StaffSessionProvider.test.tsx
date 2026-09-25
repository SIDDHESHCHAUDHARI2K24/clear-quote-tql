import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// `vi.hoisted`: the api-client mock factory runs when `lib/api-client`
// is first imported (hoisted above plain `const`s).
const { getMock, postMock, replaceMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
  replaceMock: vi.fn(),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: postMock }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

import { StaffSessionProvider, useStaffSession } from "./StaffSessionProvider";

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "lo@clearquote.test",
  full_name: "Jamie Rivera",
  role: "lo" as const,
  nmls: null,
  title: null,
  phone: null,
};

function Probe() {
  const { user, role, isAdmin, isManagerOrAdmin } = useStaffSession();
  return (
    <p data-testid="probe">
      {user.full_name}|{role}|{String(isAdmin)}|{String(isManagerOrAdmin)}
    </p>
  );
}

function renderProvider() {
  return render(
    <StaffSessionProvider>
      <Probe />
    </StaffSessionProvider>,
  );
}

describe("StaffSessionProvider", () => {
  afterEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    postMock.mockResolvedValue({ data: undefined, error: undefined });
    replaceMock.mockReset();
  });

  it("shows a checking state, then the session once /me resolves (loaded once)", async () => {
    getMock.mockResolvedValueOnce({ data: USER, error: undefined });
    renderProvider();
    expect(screen.getByRole("status")).toHaveTextContent("Checking session…");
    expect(await screen.findByTestId("probe")).toHaveTextContent("Jamie Rivera|lo|false|false");
    expect(getMock).toHaveBeenCalledTimes(1);
    expect(getMock).toHaveBeenCalledWith("/api/v1/auth/staff/me");
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it.each([
    ["manager", "false|true"],
    ["admin", "true|true"],
  ] as const)("derives the role flags for a %s", async (role, flags) => {
    getMock.mockResolvedValueOnce({ data: { ...USER, role }, error: undefined });
    renderProvider();
    expect(await screen.findByTestId("probe")).toHaveTextContent(`${role}|${flags}`);
  });

  it("clears the stale cookie then redirects to /login on a 401", async () => {
    getMock.mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "AUTHENTICATION_ERROR", message: "Not authenticated" } },
    });
    renderProvider();
    await waitFor(() => expect(postMock).toHaveBeenCalledWith("/api/v1/auth/staff/logout"));
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
    expect(screen.queryByTestId("probe")).not.toBeInTheDocument();
  });

  it("redirects to /login without throwing when /me rejects", async () => {
    getMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    expect(() => renderProvider()).not.toThrow();
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });

  it("throws a clear error when used outside the provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow(
      "useStaffSession must be used inside <StaffSessionProvider>",
    );
    spy.mockRestore();
  });
});
