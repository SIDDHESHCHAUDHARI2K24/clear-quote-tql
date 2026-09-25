// CQ-020 unit 2: the Send tab's send workflow (T10–T12), the PUT 409
// SEND_IN_PROGRESS handling and the PR #22 save-ordering minor (T13).
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, putMock, postMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  putMock: vi.fn(),
  postMock: vi.fn(),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, PUT: putMock, POST: postMock, DELETE: vi.fn() }),
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
import type { Readiness, SendPackage, SendStatus, SentVersion } from "./api";
import { SendTab } from "./SendTab";
import { SEND_IN_PROGRESS_MESSAGE } from "./useSendTab";

const pkg = packageFixture as SendPackage;
const scenarios = scenariosFixture as ScenariosView;
const report = REPORT_FIXTURES.find((f) => f.key === "marcus_hale")!.viewModel;
const READY: Readiness = { ready: true, blockers: [] };
const EMAIL = "marcus.hale@clearquote-demo.test";
const SLOW = { timeout: 5000 };

const ok = (data: unknown, status = 200) => ({
  data,
  error: undefined,
  response: { ok: true, status },
});
const fail = (status: number, code: string, message: string, details: unknown = {}) => ({
  data: undefined,
  error: { error: { code, message, details } },
  response: { ok: false, status },
});

function status(step: SendStatus["status"], extra: Partial<SendStatus> = {}): SendStatus {
  return {
    package_id: pkg.id,
    workflow_id: step === "idle" ? null : "send-package-x",
    status: step,
    error: null,
    version: null,
    recipient_email: null,
    sent_at: null,
    ...extra,
  };
}

function version(n: number, superseded: boolean): SentVersion {
  return {
    id: `00000000-0000-0000-0000-00000000000${n}`,
    version: n,
    sent_at: `2026-09-25T1${n}:00:00Z`,
    expires_at: "2026-10-16T12:00:00Z",
    superseded,
    viewed_at: null,
    report_url: `http://localhost:3210/report/token-${n}`,
    letter_url: `/api/v1/packages/${pkg.id}/letter.pdf?version=${n}`,
    outbox_email_id: `11111111-0000-0000-0000-00000000000${n}`,
    email_status: "sent",
    recipient_email: EMAIL,
  };
}

interface Serve {
  statuses?: SendStatus[];
  versions?: () => SentVersion[];
  current?: () => SendPackage;
}

/** `statuses` are returned in order by successive `send-status` polls
 * (the last one repeats). */
function serve({
  statuses = [status("idle")],
  versions = () => [],
  current = () => pkg,
}: Serve = {}) {
  const queue = [...statuses];
  getMock.mockImplementation((path: string) => {
    if (path.endsWith("/package")) return Promise.resolve(ok(current()));
    if (path.endsWith("/scenarios")) return Promise.resolve(ok(scenarios));
    if (path.endsWith("/readiness")) return Promise.resolve(ok(READY));
    if (path.endsWith("/report")) return Promise.resolve(ok(report));
    if (path.endsWith("/letter.html")) return Promise.resolve(ok("<p>letter</p>"));
    if (path.endsWith("/send-status")) {
      const next = queue.length > 1 ? queue.shift()! : queue[0];
      return Promise.resolve(ok(next));
    }
    if (path.endsWith("/versions")) return Promise.resolve(ok(versions()));
    return Promise.reject(new Error(`unexpected GET ${path}`));
  });
}

function sendStatusCalls() {
  return getMock.mock.calls.filter(([path]) => String(path).endsWith("/send-status")).length;
}

async function openDialogAndSend() {
  const button = await screen.findByRole("button", { name: "Send to borrower" });
  await waitFor(() => expect(button).toBeEnabled());
  await userEvent.click(button);
  const dialog = await screen.findByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Send" }));
  return dialog;
}

afterEach(() => {
  for (const m of [getMock, putMock, postMock, refetchWorkspace]) m.mockReset();
});

describe("Send flow (CQ-020)", () => {
  it("T10/T11/T12: Send starts the workflow, shows Rendering letter → Emailing → Done, toasts and lists the sent version", async () => {
    let sent = false;
    serve({
      statuses: [
        status("idle"), // on open
        status("rendering"),
        status("emailing"),
        status("done", { version: 1, recipient_email: EMAIL, sent_at: "2026-09-25T11:00:00Z" }),
      ],
      versions: () => (sent ? [version(1, false)] : []),
      current: () => (sent ? { ...pkg, sent_at: "2026-09-25T11:00:00Z" } : pkg),
    });
    postMock.mockImplementation(() => {
      sent = true;
      return Promise.resolve(
        ok({ package_id: pkg.id, workflow_id: "send-package-x", status: "queued" }, 202),
      );
    });
    render(<SendTab />);

    const dialog = await openDialogAndSend();
    expect(postMock).toHaveBeenCalledWith("/api/v1/packages/{package_id}/send", {
      params: { path: { package_id: pkg.id } },
    });
    const progress = within(dialog).getByTestId("send-progress");
    expect(within(progress).getByText("Rendering letter")).toHaveAttribute("aria-current", "step");
    await waitFor(
      () => expect(within(progress).getByText("Emailing")).toHaveAttribute("aria-current", "step"),
      SLOW,
    );
    await waitFor(() => expect(dialog).toHaveTextContent("✓Done"), SLOW);

    expect(await screen.findByTestId("send-toast")).toHaveTextContent(`Sent to ${EMAIL}`);
    // The status pill (workspace summary) and the package are refetched.
    expect(refetchWorkspace).toHaveBeenCalled();
    const rows = await screen.findAllByTestId("sent-version");
    expect(rows).toHaveLength(1);
    expect(within(rows[0]).getByTestId("sent-version-state")).toHaveTextContent("Current");
    expect(within(rows[0]).getByRole("link", { name: "Download PDF" })).toHaveAttribute(
      "href",
      expect.stringMatching(new RegExp(`/api/v1/packages/${pkg.id}/letter\\.pdf\\?version=1$`)),
    );
    expect(within(rows[0]).getByRole("link", { name: "Open in Outbox" })).toHaveAttribute(
      "href",
      "/outbox?email=11111111-0000-0000-0000-000000000001",
    );
    // Polling stopped at done.
    const calls = sendStatusCalls();
    await new Promise((r) => setTimeout(r, 700));
    expect(sendStatusCalls()).toBe(calls);

    // The footer's Close (the overlay's own × is also named "Close").
    const closeButtons = within(dialog).getAllByRole("button", { name: "Close" });
    await userEvent.click(closeButtons[closeButtons.length - 1]);
    expect(await screen.findByRole("button", { name: "Send to borrower" })).toBeEnabled();
  });

  it("AC4 in the UI: a 409 PACKAGE_NOT_READY shows the blockers and polls nothing", async () => {
    serve();
    postMock.mockResolvedValue(
      fail(409, "PACKAGE_NOT_READY", "The package isn't ready to send.", {
        blockers: [{ code: "quotes_stale", message: "Quotes are out of date", tab: "pricing" }],
      }),
    );
    render(<SendTab />);
    const dialog = await openDialogAndSend();

    const blocked = await within(dialog).findByTestId("send-blocked");
    expect(blocked).toHaveTextContent("The package isn't ready to send.");
    expect(blocked).toHaveTextContent("Quotes are out of date");
    const calls = sendStatusCalls();
    await new Promise((r) => setTimeout(r, 700));
    expect(sendStatusCalls()).toBe(calls);
    expect(screen.queryByTestId("send-toast")).not.toBeInTheDocument();
  });

  it("a failed send shows its error and offers Try again", async () => {
    serve({
      statuses: [status("idle"), status("failed", { error: "Quotes are out of date" })],
    });
    postMock.mockResolvedValue(
      ok({ package_id: pkg.id, workflow_id: "send-package-x", status: "queued" }, 202),
    );
    render(<SendTab />);
    const dialog = await openDialogAndSend();

    expect(await within(dialog).findByTestId("send-failed", {}, SLOW)).toHaveTextContent(
      "Send failed: Quotes are out of date",
    );
    expect(within(dialog).getByRole("button", { name: "Try again" })).toBeEnabled();
    expect(screen.queryByTestId("send-toast")).not.toBeInTheDocument();
  });

  it("a send already running when the tab opens is followed, and editing is locked", async () => {
    serve({
      statuses: [
        status("emailing"),
        status("emailing"),
        status("done", { recipient_email: EMAIL }),
      ],
    });
    render(<SendTab />);

    expect(await screen.findByRole("button", { name: "Sending…" })).toBeDisabled();
    expect(screen.getByTestId("send-progress-inline")).toHaveTextContent("Emailing");
    expect(screen.getByLabelText("Note to the borrower (optional)")).toBeDisabled();
    const firstCheckbox = within(screen.getAllByTestId("selected-quote")[0]).getByRole("checkbox");
    expect(firstCheckbox).toBeDisabled();

    expect(await screen.findByTestId("send-toast", {}, SLOW)).toHaveTextContent(`Sent to ${EMAIL}`);
    await waitFor(() =>
      expect(screen.getByLabelText("Note to the borrower (optional)")).toBeEnabled(),
    );
  });

  it("marks superseded versions and hides the links a seeded version doesn't have", async () => {
    const seeded = { ...version(1, true), letter_url: null, outbox_email_id: null };
    serve({ versions: () => [version(2, false), seeded] });
    render(<SendTab />);

    const rows = await screen.findAllByTestId("sent-version");
    expect(rows.map((r) => within(r).getByTestId("sent-version-state").textContent)).toEqual([
      "Current",
      "Superseded",
    ]);
    expect(within(rows[1]).queryByRole("link")).not.toBeInTheDocument();
  });

  it("PUT 409 SEND_IN_PROGRESS: the edit is dropped, the server package shown again and the send followed", async () => {
    serve({
      statuses: [status("idle"), status("rendering"), status("done", { recipient_email: EMAIL })],
    });
    putMock.mockResolvedValue(
      fail(
        409,
        "SEND_IN_PROGRESS",
        "This package is being sent. Try again once the send finishes.",
      ),
    );
    render(<SendTab />);
    const selected = await screen.findAllByTestId("selected-quote");
    const before = sendStatusCalls();

    await userEvent.click(within(selected[2]).getByRole("checkbox"));
    await waitFor(() =>
      expect(screen.getByTestId("save-status")).toHaveTextContent(SEND_IN_PROGRESS_MESSAGE),
    );
    // Reverted to the server's three quotes, and the send-status re-read.
    await waitFor(() => expect(screen.getAllByTestId("selected-quote")).toHaveLength(3));
    await waitFor(() => expect(sendStatusCalls()).toBeGreaterThan(before));
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(await screen.findByTestId("send-toast", {}, SLOW)).toHaveTextContent(`Sent to ${EMAIL}`);
  });
});

describe("Send-tab saves (PR #22 minor, T13)", () => {
  it("a failed save is not silently dropped by a later successful save: the later PUT carries it", async () => {
    serve();
    let call = 0;
    let serverState: SendPackage = pkg;
    putMock.mockImplementation(async (_path: string, { body }: { body: Partial<SendPackage> }) => {
      call += 1;
      if (call === 1) return fail(500, "INTERNAL", "Something broke");
      serverState = { ...serverState, ...body, updated_at: new Date().toISOString() };
      return ok(serverState);
    });
    render(<SendTab />);
    const [par, buydown] = pkg.quote_ids;
    const selected = await screen.findAllByTestId("selected-quote");

    await userEvent.click(within(selected[2]).getByRole("checkbox")); // save #1 fails
    await waitFor(() =>
      expect(screen.getByTestId("save-status")).toHaveTextContent("Something broke"),
    );

    const note = screen.getByLabelText("Note to the borrower (optional)");
    await userEvent.type(note, "Call me first.");
    await userEvent.tab(); // save #2 succeeds and must include save #1's removal
    await waitFor(() => expect(putMock).toHaveBeenCalledTimes(2));
    expect(putMock.mock.lastCall?.[1].body).toEqual({
      quote_ids: [par, buydown],
      recommended_quote_id: par,
      lo_note: "Call me first.",
    });
    await waitFor(() =>
      expect(screen.getByTestId("save-status")).toHaveTextContent("All changes saved"),
    );
    expect(serverState.quote_ids).toEqual([par, buydown]);
    expect(screen.getAllByTestId("selected-quote")).toHaveLength(2);
  });

  it("the error stays while the failed edit is unsaved, and Retry re-sends it", async () => {
    serve();
    let call = 0;
    putMock.mockImplementation(async (_path: string, { body }: { body: Partial<SendPackage> }) => {
      call += 1;
      if (call <= 2) return fail(500, "INTERNAL", "Something broke");
      return ok({ ...pkg, ...body, updated_at: new Date().toISOString() });
    });
    render(<SendTab />);
    const [par, buydown] = pkg.quote_ids;
    const selected = await screen.findAllByTestId("selected-quote");

    await userEvent.click(within(selected[2]).getByRole("checkbox")); // #1 fails
    await waitFor(() =>
      expect(screen.getByTestId("save-status")).toHaveTextContent("Something broke"),
    );
    const rows = screen.getAllByTestId("selected-quote");
    await userEvent.click(within(rows[1]).getByRole("radio")); // #2 fails too
    await waitFor(() => expect(putMock).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByTestId("save-status")).toHaveTextContent("Something broke"),
    );

    await userEvent.click(screen.getByRole("button", { name: "Retry" })); // #3 succeeds
    await waitFor(() => expect(putMock).toHaveBeenCalledTimes(3));
    expect(putMock.mock.lastCall?.[1].body).toEqual({
      quote_ids: [par, buydown],
      recommended_quote_id: buydown,
      lo_note: null,
    });
    await waitFor(() =>
      expect(screen.getByTestId("save-status")).toHaveTextContent("All changes saved"),
    );
  });
});
