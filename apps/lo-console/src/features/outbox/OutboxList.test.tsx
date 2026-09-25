import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock }),
}));

import { OutboxList } from "./OutboxList";
import type { OutboxEmailRow } from "./api";

function row(overrides: Partial<OutboxEmailRow> = {}): OutboxEmailRow {
  return {
    id: crypto.randomUUID(),
    to_email: "marcus.hale@example.com",
    subject: "Your Clear Quote pre-approval is ready",
    type: "quote_sent",
    status: "sent",
    application_id: crypto.randomUUID(),
    client_name: "Marcus Hale",
    sent_at: new Date().toISOString(),
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("OutboxList (AC2)", () => {
  afterEach(() => {
    getMock.mockReset();
  });

  it("lists emails and calls onSelect when a row is clicked", async () => {
    const onSelect = vi.fn();
    getMock.mockResolvedValueOnce({
      data: { items: [row()], total: 1, page: 1, page_size: 25 },
      response: { status: 200 },
    });

    render(<OutboxList onSelect={onSelect} />);

    expect(await screen.findByText("marcus.hale@example.com")).toBeInTheDocument();
    expect(screen.getByText("Your Clear Quote pre-approval is ready")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /marcus.hale@example.com/ }));
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ to_email: "marcus.hale@example.com" }),
    );
  });

  it("filters by type", async () => {
    getMock.mockResolvedValueOnce({
      data: { items: [row()], total: 1, page: 1, page_size: 25 },
      response: { status: 200 },
    });
    render(<OutboxList onSelect={vi.fn()} />);
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(1));

    getMock.mockResolvedValueOnce({
      data: { items: [], total: 0, page: 1, page_size: 25 },
      response: { status: 200 },
    });
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Type"), "otp");

    await waitFor(() =>
      expect(getMock).toHaveBeenLastCalledWith(
        "/api/v1/outbox",
        expect.objectContaining({
          params: expect.objectContaining({
            query: expect.objectContaining({ type: "otp" }),
          }),
        }),
      ),
    );
  });

  // Code review finding: search used to fire one GET per keystroke.
  it("debounces the search input instead of fetching on every keystroke", async () => {
    getMock.mockResolvedValueOnce({
      data: { items: [row()], total: 1, page: 1, page_size: 25 },
      response: { status: 200 },
    });
    render(<OutboxList onSelect={vi.fn()} />);
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(1));

    getMock.mockResolvedValue({
      data: { items: [], total: 0, page: 1, page_size: 25 },
      response: { status: 200 },
    });
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Search by recipient or subject"), "pre-approval");

    // Mid-typing: no new fetch yet (still debouncing).
    expect(getMock).toHaveBeenCalledTimes(1);

    await waitFor(
      () =>
        expect(getMock).toHaveBeenLastCalledWith(
          "/api/v1/outbox",
          expect.objectContaining({
            params: expect.objectContaining({
              query: expect.objectContaining({ q: "pre-approval" }),
            }),
          }),
        ),
      { timeout: 2000 },
    );
    // Exactly one fetch for the whole typed string, not one per keystroke.
    expect(getMock).toHaveBeenCalledTimes(2);
  });
});
