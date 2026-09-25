import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, pushMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  pushMock: vi.fn(),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: vi.fn() }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

import { ClientDetailView } from "./ClientDetailView";

const CLIENT_ID = "11111111-1111-1111-1111-111111111111";

const APPLICATION_ROW = {
  id: "aaaaaaaa-1111-1111-1111-111111111111",
  client_name: "Marcus Hale",
  property_label: "1500 Larimer St, Denver, CO",
  strategy: "str" as const,
  purchase_price: "410000.00",
  status: "sent" as const,
  flag_count: 0,
  lo_id: "lo-1",
  lo_name: "Jordan Lee",
  updated_at: "2026-09-20T12:00:00Z",
};

const DETAIL = {
  id: CLIENT_ID,
  name: "Marcus Hale",
  email: "marcus.hale@clearquote-demo.test",
  phone: "555-0100",
  lo_id: "lo-1",
  lo_name: "Jordan Lee",
  created_at: "2026-08-01T12:00:00Z",
  applications: [APPLICATION_ROW],
  sent_versions: [
    {
      id: "v1",
      application_id: APPLICATION_ROW.id,
      version: 1,
      sent_at: "2026-09-02T12:00:00Z",
      recommended_option_label: "30yr Fixed · Par",
      status: "viewed" as const,
      report_link: "/report/abc123",
    },
  ],
  activity: [
    {
      id: "e1",
      actor: { kind: "borrower" as const, name: "Marcus Hale" },
      type: "quote.viewed",
      message: "Viewed the quote package (v1)",
      payload_summary: null,
      at: "2026-09-03T12:00:00Z",
    },
  ],
};

describe("ClientDetailView", () => {
  afterEach(() => {
    getMock.mockReset();
    pushMock.mockReset();
  });

  it("loads and renders the client's applications, sent versions and activity", async () => {
    getMock.mockResolvedValue({ data: DETAIL, error: undefined, response: { status: 200 } });
    render(<ClientDetailView clientId={CLIENT_ID} />);

    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: "Marcus Hale" })).toBeInTheDocument(),
    );
    expect(screen.getByText("30yr Fixed · Par")).toBeInTheDocument();
    expect(screen.getByText("Viewed the quote package (v1)")).toBeInTheDocument();
  });

  it("shows the applications empty state", async () => {
    getMock.mockResolvedValue({
      data: { ...DETAIL, applications: [] },
      error: undefined,
      response: { status: 200 },
    });
    render(<ClientDetailView clientId={CLIENT_ID} />);

    await waitFor(() => expect(screen.getByText("No applications yet")).toBeInTheDocument());
  });

  it("shows an error message when the fetch fails", async () => {
    getMock.mockResolvedValue({
      data: undefined,
      error: { error: { message: "Not found" } },
      response: { status: 404 },
    });
    render(<ClientDetailView clientId={CLIENT_ID} />);

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
