import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { getMock, replaceMock, searchParamsGet } = vi.hoisted(() => ({
  getMock: vi.fn(),
  replaceMock: vi.fn(),
  searchParamsGet: vi.fn(() => null),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: vi.fn() }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  useSearchParams: () => ({ get: searchParamsGet, toString: () => "" }),
}));

import DashboardRoute from "./page";
import ClientsPage from "./clients/page";

// P5/P6 foundation: each still-reserved route renders its heading and the
// item that builds it. `/` was CQ-025's stub -- replaced by the real
// dashboard below (this file is shared with the still-stubbed routes;
// removing only the `/` row here is this item's "small necessity" edit,
// per phase-p5-p6-worker-guide.md). (The session behaviour the old
// placeholder home tested -- /me, 401 -> logout -> /login, Sign out --
// moved to src/features/shell/StaffSessionProvider.test.tsx and
// StaffShell.test.tsx.)
//
// CQ-027 (small, logged necessity): `./applications/page` is no longer a
// stub -- it needs a `StaffSessionProvider` and a mocked api-client, which
// this bare-render table doesn't set up. Its own tests are
// `applications/page.test.tsx`.
//
// CQ-029 (outbox, admin/integrations, admin/settings) replaced its three
// stub rows with real pages -- their own coverage now lives in
// src/features/{outbox,admin}/**/*.test.tsx.
describe("(staff) stub pages", () => {
  it.each([["Clients", ClientsPage, "CQ-026"]])(
    "%s says which item builds it",
    (title, Page, item) => {
      render(<Page />);
      expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
      expect(screen.getByText(`Built in ${item}`)).toBeInTheDocument();
    },
  );
});

describe("/ (CQ-025 dashboard)", () => {
  it("renders the dashboard heading once loaded", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        tiles: {
          clients: 0,
          applications: 0,
          pre_approvals_sent: 0,
          with_property: 0,
          awaiting_review: 0,
          needs_attention: 0,
          stale_quotes: 0,
        },
        attention: [],
        stale: [],
        activity: [],
        los: null,
      },
      response: { status: 200 },
    });

    render(<DashboardRoute />);

    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
  });
});
