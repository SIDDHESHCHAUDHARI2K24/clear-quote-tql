import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock }),
}));

import { OutboxDetail } from "./OutboxDetail";

const EMAIL_ID = "22222222-2222-2222-2222-222222222222";

describe("OutboxDetail (AC2/AC7)", () => {
  afterEach(() => {
    getMock.mockReset();
  });

  it("renders the HTML in a sandboxed iframe with no scripts, plus attachment links", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        id: EMAIL_ID,
        to_email: "marcus.hale@example.com",
        subject: "Your Clear Quote pre-approval is ready",
        type: "quote_sent",
        status: "sent",
        application_id: "11111111-1111-1111-1111-111111111111",
        client_name: "Marcus Hale",
        sent_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
        html: "<p>Your report is ready.</p><script>alert(1)</script>",
        attachments: [{ key: "outbox/fixture/quote.pdf", filename: "quote.pdf" }],
      },
      response: { status: 200 },
    });

    render(<OutboxDetail emailId={EMAIL_ID} />);

    expect(await screen.findByText("Marcus Hale")).toBeInTheDocument();
    const iframe = screen.getByTitle(/Your Clear Quote pre-approval is ready/);
    expect(iframe).toHaveAttribute("sandbox", "");
    expect(iframe.tagName).toBe("IFRAME");

    const link = screen.getByRole("link", { name: "quote.pdf" });
    expect(link).toHaveAttribute(
      "href",
      expect.stringContaining("/attachments/outbox/fixture/quote.pdf"),
    );
  });

  it("shows an error message when the email can't be loaded", async () => {
    getMock.mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "NOT_FOUND", message: "Outbox email not found" } },
      response: { status: 404 },
    });

    render(<OutboxDetail emailId={EMAIL_ID} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Outbox email not found");
  });
});
