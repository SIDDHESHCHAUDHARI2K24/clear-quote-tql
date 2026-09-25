import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, postMock, putMock, deleteMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  putMock: vi.fn(),
  deleteMock: vi.fn(),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: postMock, PUT: putMock, DELETE: deleteMock }),
}));

const APP_ID = "11111111-1111-1111-1111-111111111111";
const refetchWorkspace = vi.fn();
vi.mock("../workspace", () => ({
  useWorkspace: () => ({ applicationId: APP_ID, refetch: refetchWorkspace }),
}));

import type { ScenariosView } from "./api";
import marcusFixture from "./__fixtures__/scenarios-marcus-hale.json";
import productsFixture from "./__fixtures__/products-marcus-hale.json";
import { QuoteBuilder } from "./QuoteBuilder";

const marcus = marcusFixture as ScenariosView;
const ok = (data: unknown) => ({ data, error: undefined, response: { ok: true, status: 200 } });
const fail = (status: number, error: unknown) => ({
  data: undefined,
  error,
  response: { ok: false, status },
});

function withQuotes(view: ScenariosView, patch: Record<string, unknown>): ScenariosView {
  return {
    ...view,
    groups: view.groups.map((g) => ({ ...g, quotes: g.quotes.map((q) => ({ ...q, ...patch })) })),
  };
}

afterEach(() => {
  for (const m of [getMock, postMock, putMock, deleteMock, refetchWorkspace]) m.mockReset();
});

describe("QuoteBuilder", () => {
  it("AC5: starring a quote recommends it and refreshes the header", async () => {
    const buydown = marcus.groups[0].quotes[1];
    const recommended: ScenariosView = {
      ...marcus,
      recommended_quote_id: buydown.id,
      groups: marcus.groups.map((g) => ({
        ...g,
        quotes: g.quotes.map((q) => ({ ...q, recommended: q.id === buydown.id })),
      })),
    };
    getMock.mockResolvedValueOnce(ok(marcus)).mockResolvedValueOnce(ok(recommended));
    postMock.mockResolvedValueOnce(
      ok({ application_id: APP_ID, recommended_quote_id: buydown.id }),
    );

    render(<QuoteBuilder hasStaleQuotes={false} />);
    const star = (await screen.findAllByRole("button", { name: "Recommend Buydown 7.375%" }))[0];
    await userEvent.click(star);

    await waitFor(() => expect(refetchWorkspace).toHaveBeenCalled());
    expect(postMock).toHaveBeenCalledWith("/api/v1/quotes/{quote_id}/recommend", {
      params: { path: { quote_id: buydown.id } },
    });
    const pressed = screen.getAllByRole("button", { pressed: true });
    expect(pressed).toHaveLength(1);
    expect(pressed[0]).toHaveAccessibleName("Buydown 7.375% is recommended");
  });

  it("AC6: a missing field shows 'Cannot price: missing Occupancy' with a link, and creates nothing", async () => {
    getMock.mockResolvedValue(
      ok({ application_id: APP_ID, strategy: null, recommended_quote_id: null, groups: [] }),
    );
    postMock.mockResolvedValueOnce(
      fail(422, {
        error: {
          code: "missing_field",
          message: "Cannot price: missing Occupancy",
          details: { field: "Occupancy", tab: "property", missing_fields: ["Occupancy"] },
        },
      }),
    );

    render(<QuoteBuilder hasStaleQuotes={false} />);
    await userEvent.click(await screen.findByRole("button", { name: "Add scenario" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Purchase price"), "300000");
    await userEvent.type(within(dialog).getByLabelText("Down payment percent"), "25");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save & AutoQuote" }));

    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent("Cannot price: missing Occupancy");
    expect(within(alert).getByRole("link")).toHaveAttribute(
      "href",
      `/applications/${APP_ID}/property`,
    );
    expect(putMock).not.toHaveBeenCalled();
    expect(postMock).toHaveBeenCalledTimes(1);
  });

  it("AC8: Re-price calls /reprice, then the stale banner clears", async () => {
    getMock
      .mockResolvedValueOnce(ok(withQuotes(marcus, { stale: true })))
      .mockResolvedValueOnce(ok(marcus));
    postMock.mockResolvedValueOnce(ok({ application_id: APP_ID, quote_ids: [], priced_at: "x" }));

    render(<QuoteBuilder hasStaleQuotes />);
    const banner = await screen.findByText("Quotes are out of date — Re-price");
    await userEvent.click(within(banner.parentElement as HTMLElement).getByRole("button"));

    await waitFor(() =>
      expect(screen.queryByText("Quotes are out of date — Re-price")).not.toBeInTheDocument(),
    );
    expect(postMock).toHaveBeenCalledWith("/api/v1/applications/{application_id}/reprice", {
      params: { path: { application_id: APP_ID } },
    });
  });

  it("uses the pricing view's stale flag until its own data loads", () => {
    getMock.mockReturnValue(new Promise(() => {}));
    render(<QuoteBuilder hasStaleQuotes />);
    expect(screen.getByText("Quotes are out of date — Re-price")).toBeInTheDocument();
  });

  it("Choose manually lists every product and saves the picked row", async () => {
    getMock
      .mockResolvedValueOnce(ok(marcus))
      .mockResolvedValueOnce(ok(productsFixture))
      .mockResolvedValue(ok(marcus));
    putMock.mockResolvedValueOnce(ok(marcus.groups[0]));
    postMock.mockResolvedValueOnce(ok({ id: "new" }));

    render(<QuoteBuilder hasStaleQuotes={false} />);
    const group = await screen.findByRole("region", { name: "At DSCR 1.00" });
    await userEvent.click(within(group).getByRole("button", { name: "Edit scenario" }));
    await userEvent.click(screen.getByRole("button", { name: "Choose manually" }));

    const rows = await screen.findAllByTestId("product-row");
    expect(rows.length).toBeGreaterThanOrEqual(8);
    await userEvent.click(within(rows[0]).getByRole("button", { name: /^Choose / }));
    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith("/api/v1/scenarios/{scenario_id}/quotes", {
        params: { path: { scenario_id: marcus.groups[0].id } },
        body: expect.objectContaining({ label: "Manual" }),
      }),
    );
  });

  it("Compare shows 2 selected quotes side by side with the report's rows", async () => {
    getMock.mockResolvedValueOnce(ok(marcus));
    render(<QuoteBuilder hasStaleQuotes={false} />);
    const boxes = await screen.findAllByRole("checkbox");
    await userEvent.click(boxes[0]);
    await userEvent.click(boxes[1]);
    await userEvent.click(screen.getByRole("button", { name: "Compare (2)" }));
    const table = within(screen.getByRole("dialog")).getByRole("table");
    const rowNames = within(table)
      .getAllByRole("rowheader")
      .map((cell) => cell.textContent);
    expect(rowNames).toEqual([
      "Rate",
      "Points",
      "Down payment",
      "Prepayment penalty",
      "Monthly payment",
      "Cash to close",
      "Monthly cashflow",
      "DSCR",
    ]);
    expect(within(table).getAllByRole("columnheader")).toHaveLength(3);
  });
});
