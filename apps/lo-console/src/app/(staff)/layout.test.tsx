import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useToast } from "@cq/ui";

// `vi.hoisted`: the api-client mock factory runs when `lib/api-client`
// is first imported (hoisted above plain `const`s).
const { getMock, postMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: postMock }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/",
}));

import StaffLayout from "./layout";

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "lo@clearquote.test",
  full_name: "Jordan Lee",
  role: "lo" as const,
  nmls: null,
  title: null,
  phone: null,
};

// Review round 1: `ToastProvider` must be mounted above `StaffSessionProvider`
// / `StaffShell` in this layout so any page under `(staff)` can call
// `useToast()`. This renders a page-level child (not `StaffShell` itself)
// to prove the provider reaches that far down the tree.
function ToastTrigger() {
  const { show } = useToast();
  return (
    <button type="button" onClick={() => show("Saved", { tone: "success" })}>
      Trigger toast
    </button>
  );
}

describe("(staff) layout", () => {
  afterEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    postMock.mockResolvedValue({ data: undefined, error: undefined });
  });

  it("mounts ToastProvider above the shell so a page child's useToast() works", async () => {
    getMock.mockResolvedValueOnce({ data: USER, error: undefined });
    const user = userEvent.setup();
    render(
      <StaffLayout>
        <ToastTrigger />
      </StaffLayout>,
    );

    await user.click(await screen.findByRole("button", { name: "Trigger toast" }));

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(screen.getByRole("status")).toContainElement(screen.getByText("Saved"));
  });
});
