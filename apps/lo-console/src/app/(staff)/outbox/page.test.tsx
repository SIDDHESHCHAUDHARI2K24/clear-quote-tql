import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, replaceMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  replaceMock: vi.fn(),
}));

let currentSearch = "";

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: vi.fn() }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  useSearchParams: () => new URLSearchParams(currentSearch),
}));

import OutboxPage from "./page";

const EMAIL_ID = "11111111-0000-0000-0000-000000000001";

function mockRoutes() {
  getMock.mockImplementation((path: string) => {
    if (path === "/api/v1/outbox") {
      return Promise.resolve({
        data: { items: [], total: 0, page: 1, page_size: 25 },
        error: undefined,
        response: { status: 200 },
      });
    }
    if (path === "/api/v1/outbox/{email_id}") {
      return Promise.resolve({
        data: {
          id: EMAIL_ID,
          to_email: "marcus.hale@example.com",
          subject: "Your pre-approval and numbers from Total Quality Lending",
          type: "quote_sent",
          status: "sent",
          application_id: "22222222-2222-2222-2222-222222222222",
          client_name: "Marcus Hale",
          sent_at: new Date().toISOString(),
          created_at: new Date().toISOString(),
          html: "<p>Hi</p>",
          attachments: [],
        },
        error: undefined,
        response: { status: 200 },
      });
    }
    return Promise.resolve({ data: undefined, error: undefined, response: { status: 404 } });
  });
}

describe("OutboxPage", () => {
  afterEach(() => {
    getMock.mockReset();
    replaceMock.mockReset();
    currentSearch = "";
  });

  it("opens the detail drawer from ?email_id= (CQ-020's Open in Outbox link)", async () => {
    currentSearch = `email_id=${EMAIL_ID}`;
    mockRoutes();

    render(<OutboxPage />);

    expect(await screen.findByText("Marcus Hale")).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith(
      "/api/v1/outbox/{email_id}",
      expect.objectContaining({ params: { path: { email_id: EMAIL_ID } } }),
    );
  });

  it("does not render the detail drawer without ?email_id=", async () => {
    mockRoutes();

    render(<OutboxPage />);

    await screen.findByText("Outbox");
    expect(screen.queryByText("Marcus Hale")).not.toBeInTheDocument();
  });
});
