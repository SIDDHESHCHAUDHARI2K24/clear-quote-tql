import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, putMock } = vi.hoisted(() => ({ getMock: vi.fn(), putMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, PUT: putMock, POST: vi.fn(), DELETE: vi.fn() }),
}));

const APP_ID = "b68af658-85fb-46c4-bd77-de630273046f";
const refetchWorkspace = vi.fn();
vi.mock("../workspace", () => ({
  useWorkspace: () => ({ applicationId: APP_ID, refetch: refetchWorkspace }),
}));

import { REPORT_FIXTURES } from "@cq/ui";

import scenariosFixture from "../quote-builder/__fixtures__/scenarios-marcus-hale.json";
import type { ScenariosView } from "../quote-builder/api";
import packageFixture from "./__fixtures__/package-marcus-hale.json";
import type { Readiness, SendPackage } from "./api";
import { SendTab } from "./SendTab";

const pkg = packageFixture as SendPackage;
const scenarios = scenariosFixture as ScenariosView;
const report = REPORT_FIXTURES.find((f) => f.key === "marcus_hale")!.viewModel;
const LETTER = "<!doctype html><html><body><p>Pre-approval letter</p></body></html>";
const READY: Readiness = { ready: true, blockers: [] };
const ok = (data: unknown) => ({ data, error: undefined, response: { ok: true, status: 200 } });
const fail = (message: string) => ({
  data: undefined,
  error: { error: { message } },
  response: { ok: false, status: 500 },
});

function serve(readiness: Readiness = READY, current: SendPackage = pkg) {
  getMock.mockImplementation((path: string) => {
    if (path.endsWith("/package")) return Promise.resolve(ok(current));
    if (path.endsWith("/scenarios")) return Promise.resolve(ok(scenarios));
    if (path.endsWith("/readiness")) return Promise.resolve(ok(readiness));
    if (path.endsWith("/report")) return Promise.resolve(ok(report));
    if (path.endsWith("/letter.html")) return Promise.resolve(ok(LETTER));
    if (path.endsWith("/send-status")) {
      return Promise.resolve(
        ok({
          package_id: current.id,
          workflow_id: null,
          status: "idle",
          error: null,
          version: null,
          recipient_email: null,
          sent_at: null,
        }),
      );
    }
    if (path.endsWith("/versions")) return Promise.resolve(ok([]));
    return Promise.reject(new Error(`unexpected GET ${path}`));
  });
}

afterEach(() => {
  for (const m of [getMock, putMock, refetchWorkspace]) m.mockReset();
});

describe("SendTab", () => {
  it("AC1: shows the default draft, recommendation text and the report preview", async () => {
    serve();
    render(<SendTab />);

    const selected = await screen.findAllByTestId("selected-quote");
    expect(selected).toHaveLength(3);
    expect(within(selected[0]).getByRole("radio")).toBeChecked();
    expect(screen.getByTestId("recommendation-text")).toHaveTextContent(
      "25% down · Par pricing at 7.625%, 5-year prepay.",
    );
    // The other quote is offered but can't be added past 3.
    const others = screen.getByRole("list", { name: "Other quotes" });
    expect(within(others).getByRole("checkbox")).toBeDisabled();
    // The preview is the portal's own ReportPage.
    const preview = await screen.findByTestId("report-preview");
    await waitFor(() => expect(preview).toHaveTextContent(/here are your numbers/i));
  });

  it("AC7: the letter renders in a sandboxed iframe that cannot run scripts", async () => {
    serve();
    render(<SendTab />);
    await userEvent.click(await screen.findByRole("tab", { name: /Pre-approval letter/ }));

    const frame = await screen.findByTestId("letter-frame");
    expect(frame.tagName).toBe("IFRAME");
    expect(frame).toHaveAttribute("sandbox", "");
    expect(frame.getAttribute("sandbox")).not.toContain("allow-scripts");
    expect(frame.getAttribute("srcdoc")).toBe(LETTER);
  });

  it("AC5: Send is disabled with the first blocker as its tooltip; blockers link to their tab", async () => {
    serve({
      ready: false,
      blockers: [
        { code: "quotes_stale", message: "Quotes are out of date", tab: "pricing" },
        { code: "borrower_email_missing", message: "Borrower email is missing", tab: "borrowers" },
      ],
    });
    render(<SendTab />);

    const button = await screen.findByRole("button", { name: "Send to borrower" });
    await waitFor(() =>
      expect(screen.getByTestId("send-button-wrapper")).toHaveAttribute(
        "title",
        "Quotes are out of date",
      ),
    );
    expect(button).toBeDisabled();
    expect(screen.getByRole("link", { name: "Go to Pricing" })).toHaveAttribute(
      "href",
      `/applications/${APP_ID}/pricing`,
    );
  });

  it("when ready, Send opens a confirm dialog with the recipient and attachments", async () => {
    serve();
    render(<SendTab />);
    const button = await screen.findByRole("button", { name: "Send to borrower" });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("send-recipient")).toHaveTextContent(
      "marcus.hale@clearquote-demo.test",
    );
    expect(dialog).toHaveTextContent("Pre-approval letter (PDF)");
    // Cancel sends nothing (the send itself: SendFlow.test.tsx).
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("AC6: removing a quote, changing the recommendation and editing the note are saved", async () => {
    serve();
    const [par, buydown, par2] = pkg.quote_ids;
    putMock.mockImplementation((_path: string, { body }: { body: Partial<SendPackage> }) =>
      Promise.resolve(ok({ ...pkg, ...body, updated_at: new Date().toISOString() })),
    );
    render(<SendTab />);
    const selected = await screen.findAllByTestId("selected-quote");

    await userEvent.click(within(selected[2]).getByRole("checkbox"));
    await waitFor(() =>
      expect(putMock).toHaveBeenLastCalledWith("/api/v1/applications/{application_id}/package", {
        params: { path: { application_id: APP_ID } },
        body: { quote_ids: [par, buydown], recommended_quote_id: par, lo_note: null },
      }),
    );
    expect(par2).toBeDefined();

    const rows = await screen.findAllByTestId("selected-quote");
    await userEvent.click(within(rows[1]).getByRole("radio"));
    await waitFor(() =>
      expect(putMock.mock.lastCall?.[1].body).toEqual({
        quote_ids: [par, buydown],
        recommended_quote_id: buydown,
        lo_note: null,
      }),
    );

    const note = screen.getByLabelText("Note to the borrower (optional)");
    await userEvent.type(note, "Call me first.");
    await userEvent.tab();
    await waitFor(() => expect(putMock.mock.lastCall?.[1].body.lo_note).toBe("Call me first."));
  });

  it("M1: a note-blur save and a checkbox save in quick succession end with the server state containing both", async () => {
    serve();
    let serverState: SendPackage = pkg;
    let releaseFirstSave: (() => void) | null = null;
    const gate = new Promise<void>((resolve) => {
      releaseFirstSave = resolve;
    });
    putMock.mockImplementation(async (_path: string, { body }: { body: Partial<SendPackage> }) => {
      if (serverState === pkg) await gate; // only the first PUT waits
      serverState = { ...serverState, ...body, updated_at: new Date().toISOString() };
      return ok(serverState);
    });
    render(<SendTab />);
    const selected = await screen.findAllByTestId("selected-quote");

    // Fire a note edit and then a checkbox removal without waiting for
    // either PUT to land.
    const note = screen.getByLabelText("Note to the borrower (optional)");
    await userEvent.type(note, "Call me first.");
    await userEvent.tab(); // blurs the note field: queues save #1 (gated)
    await userEvent.click(within(selected[2]).getByRole("checkbox")); // queues save #2

    // Save #2 must not fire until save #1's response has landed.
    expect(putMock).toHaveBeenCalledTimes(1);
    releaseFirstSave!();
    await waitFor(() => expect(putMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(serverState.lo_note).toBe("Call me first."));
    expect(serverState.quote_ids).toEqual([pkg.quote_ids[0], pkg.quote_ids[1]]);
    await waitFor(() =>
      expect(screen.getByTestId("save-status")).toHaveTextContent("All changes saved"),
    );
  });

  it("post-merge review follow-up: a later save's success clears an earlier save's error", async () => {
    serve();
    let call = 0;
    putMock.mockImplementation(async (_path: string, { body }: { body: Partial<SendPackage> }) => {
      call += 1;
      if (call === 1) return fail("Something broke");
      return ok({ ...pkg, ...body, updated_at: new Date().toISOString() });
    });
    render(<SendTab />);
    const selected = await screen.findAllByTestId("selected-quote");

    await userEvent.click(within(selected[2]).getByRole("checkbox")); // save #1: fails
    await waitFor(() =>
      expect(screen.getByTestId("save-status")).toHaveTextContent("Something broke"),
    );
    // The failed save's optimistic edit stays on screen (not reverted):
    // reverting it would also wipe out an edit still queued behind it.
    expect(screen.getAllByTestId("selected-quote")).toHaveLength(2);

    const rows = await screen.findAllByTestId("selected-quote");
    await userEvent.click(within(rows[1]).getByRole("radio")); // save #2: succeeds
    await waitFor(() =>
      expect(screen.getByTestId("save-status")).toHaveTextContent("All changes saved"),
    );
  });

  it("reorders with the keyboard-accessible move buttons", async () => {
    serve();
    putMock.mockImplementation((_path: string, { body }: { body: Partial<SendPackage> }) =>
      Promise.resolve(ok({ ...pkg, ...body })),
    );
    render(<SendTab />);
    const rows = await screen.findAllByTestId("selected-quote");
    await userEvent.click(within(rows[0]).getByRole("button", { name: /Move .* down/ }));
    await waitFor(() =>
      expect(putMock.mock.lastCall?.[1].body.quote_ids).toEqual([
        pkg.quote_ids[1],
        pkg.quote_ids[0],
        pkg.quote_ids[2],
      ]),
    );
  });
});
