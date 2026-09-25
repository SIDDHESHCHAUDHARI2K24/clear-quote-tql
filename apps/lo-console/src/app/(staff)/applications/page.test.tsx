import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// `vi.hoisted`: the api-client mock factory runs when `lib/api-client` is
// first imported (hoisted above plain `const`s).
const { getMock, pushMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  pushMock: vi.fn(),
}));
let currentSearch = "";

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: vi.fn() }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
  usePathname: () => "/applications",
  useSearchParams: () => new URLSearchParams(currentSearch),
}));

import { StaffSessionProvider } from "../../../features/shell";
import ApplicationsPage from "./page";

const LO_USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "lo@clearquote.test",
  full_name: "Jordan Lee",
  role: "lo" as const,
  nmls: null,
  title: null,
  phone: null,
};

const MANAGER_USER = { ...LO_USER, role: "manager" as const, full_name: "Sam Manager" };

const ROW = {
  id: "aaaaaaaa-1111-1111-1111-111111111111",
  client_name: "Aisha Coleman",
  property_label: "450 W Broad St, Columbus, OH",
  strategy: "ltr" as const,
  purchase_price: "310000.00",
  status: "needs_attention" as const,
  flag_count: 1,
  lo_id: LO_USER.id,
  lo_name: "Jordan Lee",
  updated_at: "2026-09-20T12:00:00Z",
};

function mockRoutes(user: typeof LO_USER | typeof MANAGER_USER, listResponse: object) {
  getMock.mockImplementation((path: string) => {
    if (path === "/api/v1/auth/staff/me") {
      return Promise.resolve({ data: user, error: undefined, response: { status: 200 } });
    }
    if (path === "/api/v1/applications") {
      return Promise.resolve({ data: listResponse, error: undefined, response: { status: 200 } });
    }
    if (path === "/api/v1/applications/los") {
      return Promise.resolve({
        data: [{ id: "lo-2", full_name: "Other LO" }],
        error: undefined,
        response: { status: 200 },
      });
    }
    return Promise.resolve({ data: undefined, error: undefined, response: { status: 404 } });
  });
}

describe("ApplicationsPage", () => {
  afterEach(() => {
    getMock.mockReset();
    pushMock.mockReset();
    currentSearch = "";
  });

  it("loads and renders the filtered, paginated table", async () => {
    mockRoutes(LO_USER, { items: [ROW], total: 1, page: 1, page_size: 25 });
    render(
      <StaffSessionProvider>
        <ApplicationsPage />
      </StaffSessionProvider>,
    );

    await waitFor(() => expect(screen.getByText("Aisha Coleman")).toBeInTheDocument());
    expect(screen.getByText("Showing 1–1 of 1")).toBeInTheDocument();
    // An LO never sees the LO filter (spec.md: Manager/Admin only).
    expect(screen.queryByLabelText("LO")).not.toBeInTheDocument();
  });

  it("shows the LO filter for a Manager and populates it", async () => {
    mockRoutes(MANAGER_USER, { items: [], total: 0, page: 1, page_size: 25 });
    render(
      <StaffSessionProvider>
        <ApplicationsPage />
      </StaffSessionProvider>,
    );

    await waitFor(() => expect(screen.getByLabelText("LO")).toBeInTheDocument());
    expect(await screen.findByText("Other LO")).toBeInTheDocument();
  });

  it("navigates to the workspace on row click", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    mockRoutes(LO_USER, { items: [ROW], total: 1, page: 1, page_size: 25 });
    render(
      <StaffSessionProvider>
        <ApplicationsPage />
      </StaffSessionProvider>,
    );

    await waitFor(() => expect(screen.getByText("Aisha Coleman")).toBeInTheDocument());
    await userEvent.click(screen.getByText("Aisha Coleman"));
    expect(pushMock).toHaveBeenCalledWith(`/applications/${ROW.id}`);
  });

  it("accepts a dashboard tile link (?status=sent_or_later)", async () => {
    currentSearch = "status=sent_or_later";
    mockRoutes(LO_USER, { items: [ROW], total: 1, page: 1, page_size: 25 });
    render(
      <StaffSessionProvider>
        <ApplicationsPage />
      </StaffSessionProvider>,
    );

    await waitFor(() =>
      expect(getMock).toHaveBeenCalledWith(
        "/api/v1/applications",
        expect.objectContaining({
          params: { query: expect.objectContaining({ status: "sent_or_later" }) },
        }),
      ),
    );
  });
});
