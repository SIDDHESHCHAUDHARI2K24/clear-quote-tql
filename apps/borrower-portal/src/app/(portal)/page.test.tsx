import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// `vi.hoisted`: the api-client mock factory runs when `lib/api-client` is
// first imported (hoisted above plain `const`s).
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
  usePathname: () => "/",
}));

import { BorrowerSessionProvider } from "../../features/shell";
import HomePage from "./page";
import ApplyPage from "./apply/page";
import CreditCheckTaskPage from "./tasks/credit-check/[id]/page";

const BORROWER_ME = {
  account_id: "11111111-1111-1111-1111-111111111111",
  email: "borrower@clearquote.test",
  client_id: "22222222-2222-2222-2222-222222222222",
  full_name: "Casey Morgan",
  first_name: "Casey",
  latest_application: null as { id: string; status: string } | null,
};

function renderHome() {
  return render(
    <BorrowerSessionProvider>
      <HomePage />
    </BorrowerSessionProvider>,
  );
}

describe("(portal) home placeholder", () => {
  afterEach(() => {
    getMock.mockReset();
    replaceMock.mockReset();
  });

  it("greets the borrower and says there is no application yet", async () => {
    getMock.mockResolvedValueOnce({ data: BORROWER_ME, error: undefined });
    renderHome();
    expect(await screen.findByRole("heading", { name: "Hi Casey" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("No application yet");
    expect(screen.getByText("Built in CQ-031")).toBeInTheDocument();
  });

  it("shows the latest application's borrower-facing status label", async () => {
    getMock.mockResolvedValueOnce({
      data: { ...BORROWER_ME, latest_application: { id: "a1", status: "priced" } },
      error: undefined,
    });
    renderHome();
    expect(await screen.findByText("Pre-approved")).toHaveAttribute("role", "status");
  });
});

// CQ-034 built `/support` (no longer a stub) -- its own tests live in
// `src/features/support/SupportForm.test.tsx`.
describe("(portal) stub pages", () => {
  it.each([
    ["Apply", ApplyPage, "CQ-032"],
    ["Credit check", CreditCheckTaskPage, "CQ-033"],
  ])("%s says which item builds it", (title, Page, item) => {
    render(<Page />);
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
    expect(screen.getByText(`Built in ${item}`)).toBeInTheDocument();
  });
});
