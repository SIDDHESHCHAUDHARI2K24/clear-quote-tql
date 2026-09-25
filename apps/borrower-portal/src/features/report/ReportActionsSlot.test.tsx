import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { REPORT_FIXTURES } from "@cq/ui";

const { getMock, postMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: postMock }),
}));

import { ReportActionsSlot } from "./ReportActionsSlot";

const marcusHale = REPORT_FIXTURES.find((f) => f.key === "marcus_hale")!.viewModel;
const marcusHaleExpired = REPORT_FIXTURES.find((f) => f.key === "marcus_hale_expired")!.viewModel;
const priyaSuperseded = REPORT_FIXTURES.find((f) => f.key === "priya_nair_superseded")!.viewModel;

function ok(data: unknown) {
  return { data, error: undefined, response: { status: 200 } };
}

function conflict() {
  return {
    data: undefined,
    error: { error: { code: "CONFLICT", message: "x", details: {} } },
    response: { status: 409 },
  };
}

function networkFailure() {
  return {
    data: undefined,
    error: { error: { code: "APP_ERROR", message: "boom" } },
    response: { status: 500 },
  };
}

const noop = () => {};

describe("ReportActionsSlot", () => {
  afterEach(() => {
    getMock.mockReset();
    postMock.mockReset();
  });

  it("shows both action buttons when the report is open", () => {
    render(
      <ReportActionsSlot
        viewModel={marcusHale}
        selectedOption={marcusHale.options[0]!}
        token="tok_abc"
        borrowerAction={null}
        onActionTaken={noop}
      />,
    );

    expect(
      screen.getByRole("button", { name: /move forward with this option/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ask about another option/i })).toBeInTheDocument();
  });

  it("carries the selected option's quote_id for e2e/testing to read", () => {
    render(
      <ReportActionsSlot
        viewModel={marcusHale}
        selectedOption={marcusHale.options[0]!}
        token="tok_abc"
        borrowerAction={null}
        onActionTaken={noop}
      />,
    );

    expect(screen.getByTestId("actions-slot")).toHaveAttribute(
      "data-selected-quote-id",
      marcusHale.options[0]!.quote_id,
    );
  });

  it("renders nothing once the version is superseded (SupersededBanner handles that instead)", () => {
    const { container } = render(
      <ReportActionsSlot
        viewModel={priyaSuperseded}
        selectedOption={priyaSuperseded.options[0]!}
        token="tok_abc"
        borrowerAction={null}
        onActionTaken={noop}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows only 'Ask for updated numbers' once expired", () => {
    render(
      <ReportActionsSlot
        viewModel={marcusHaleExpired}
        selectedOption={marcusHaleExpired.options[0]!}
        token="tok_abc"
        borrowerAction={null}
        onActionTaken={noop}
      />,
    );

    expect(screen.getByRole("button", { name: /ask for updated numbers/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /move forward with this option/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /ask about another option/i }),
    ).not.toBeInTheDocument();
  });

  it("calls ask_updated and calls onActionTaken when expired 'Ask for updated numbers' is clicked", async () => {
    postMock.mockResolvedValueOnce(
      ok({
        status: "inquiry",
        borrower_action: { type: "ask_updated" },
        at: "2026-09-25T00:00:00Z",
      }),
    );
    const onActionTaken = vi.fn();
    const user = userEvent.setup();
    render(
      <ReportActionsSlot
        viewModel={marcusHaleExpired}
        selectedOption={marcusHaleExpired.options[0]!}
        token="tok_abc"
        borrowerAction={null}
        onActionTaken={onActionTaken}
      />,
    );

    await user.click(screen.getByRole("button", { name: /ask for updated numbers/i }));

    await waitFor(() => expect(onActionTaken).toHaveBeenCalled());
    expect(postMock).toHaveBeenCalledWith(
      "/api/v1/portal/reports/{token}/actions",
      expect.objectContaining({
        params: { path: { token: "tok_abc" } },
        body: { type: "ask_updated" },
      }),
    );
  });

  it("shows the confirmed state after a move_forward borrower_action, with no buttons", () => {
    render(
      <ReportActionsSlot
        viewModel={marcusHale}
        selectedOption={marcusHale.options[0]!}
        token="tok_abc"
        borrowerAction={{
          type: "move_forward",
          quote_id: marcusHale.options[1]!.quote_id,
          message: null,
          at: "2026-09-25T00:00:00Z",
        }}
        onActionTaken={noop}
      />,
    );

    expect(screen.getByText(new RegExp(marcusHale.options[1]!.label))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(marcusHale.lo.name))).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /move forward with this option/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /ask about another option/i }),
    ).not.toBeInTheDocument();
  });

  it("move forward: opens a confirm dialog with the exact spec.md wording, submits on confirm", async () => {
    postMock.mockResolvedValueOnce(
      ok({
        status: "option_selected",
        borrower_action: { type: "move_forward" },
        at: "2026-09-25T00:00:00Z",
      }),
    );
    const onActionTaken = vi.fn();
    const user = userEvent.setup();
    render(
      <ReportActionsSlot
        viewModel={marcusHale}
        selectedOption={marcusHale.options[0]!}
        token="tok_abc"
        borrowerAction={null}
        onActionTaken={onActionTaken}
      />,
    );

    await user.click(screen.getByRole("button", { name: /move forward with this option/i }));

    const loFirstName = marcusHale.lo.name.split(" ")[0];
    expect(
      screen.getByText(new RegExp(`This tells ${loFirstName} you.d like to go ahead with`)),
    ).toBeInTheDocument();
    expect(screen.getByText(/isn.t locked yet/i)).toBeInTheDocument();

    // AC5: "locked" (whole word "lock" bounded on both sides) is fine to
    // scan for and not match, since "locked" itself never matches a
    // word-boundary "lock" pattern -- only the bare word would.
    const dialogText = screen.getByRole("dialog").textContent ?? "";
    expect(dialogText).not.toMatch(/\baccept\w*\b/i);
    expect(dialogText).not.toMatch(/\block\b/i);
    expect(dialogText).not.toMatch(/\bapproved rate\b/i);

    await user.click(
      screen.getByRole("button", { name: new RegExp(`Yes, let ${loFirstName} know`) }),
    );

    await waitFor(() => expect(onActionTaken).toHaveBeenCalled());
    expect(postMock).toHaveBeenCalledWith(
      "/api/v1/portal/reports/{token}/actions",
      expect.objectContaining({
        params: { path: { token: "tok_abc" } },
        body: { type: "move_forward", quote_id: marcusHale.options[0]!.quote_id },
      }),
    );
  });

  it("ask about another option: requires a message before Send is enabled, then submits it", async () => {
    postMock.mockResolvedValueOnce(
      ok({ status: "inquiry", borrower_action: { type: "ask_other" }, at: "2026-09-25T00:00:00Z" }),
    );
    const onActionTaken = vi.fn();
    const user = userEvent.setup();
    render(
      <ReportActionsSlot
        viewModel={marcusHale}
        selectedOption={marcusHale.options[0]!}
        token="tok_abc"
        borrowerAction={null}
        onActionTaken={onActionTaken}
      />,
    );

    await user.click(screen.getByRole("button", { name: /ask about another option/i }));
    expect(screen.getByPlaceholderText(/what would you like to change/i)).toBeInTheDocument();

    const sendButton = screen.getByRole("button", { name: /send message/i });
    expect(sendButton).toBeDisabled();

    await user.type(screen.getByLabelText(/your message/i), "A lower cash to close, please.");
    expect(sendButton).not.toBeDisabled();
    await user.click(sendButton);

    await waitFor(() => expect(onActionTaken).toHaveBeenCalled());
    expect(postMock).toHaveBeenCalledWith(
      "/api/v1/portal/reports/{token}/actions",
      expect.objectContaining({
        body: {
          type: "ask_other",
          quote_id: marcusHale.options[0]!.quote_id,
          message: "A lower cash to close, please.",
        },
      }),
    );
  });

  it("409 closes the dialog and refetches instead of showing an error", async () => {
    postMock.mockResolvedValueOnce(conflict());
    const onActionTaken = vi.fn();
    const user = userEvent.setup();
    render(
      <ReportActionsSlot
        viewModel={marcusHale}
        selectedOption={marcusHale.options[0]!}
        token="tok_abc"
        borrowerAction={null}
        onActionTaken={onActionTaken}
      />,
    );

    await user.click(screen.getByRole("button", { name: /move forward with this option/i }));
    const loFirstName = marcusHale.lo.name.split(" ")[0];
    await user.click(
      screen.getByRole("button", { name: new RegExp(`Yes, let ${loFirstName} know`) }),
    );

    await waitFor(() => expect(onActionTaken).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a network failure shows a retry message inside the dialog, not a silent failure", async () => {
    postMock.mockResolvedValueOnce(networkFailure());
    const user = userEvent.setup();
    render(
      <ReportActionsSlot
        viewModel={marcusHale}
        selectedOption={marcusHale.options[0]!}
        token="tok_abc"
        borrowerAction={null}
        onActionTaken={noop}
      />,
    );

    await user.click(screen.getByRole("button", { name: /move forward with this option/i }));
    const loFirstName = marcusHale.lo.name.split(" ")[0];
    await user.click(
      screen.getByRole("button", { name: new RegExp(`Yes, let ${loFirstName} know`) }),
    );

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("no wording says accept, lock or approved rate (AC5)", () => {
    render(
      <ReportActionsSlot
        viewModel={marcusHale}
        selectedOption={marcusHale.options[0]!}
        token="tok_abc"
        borrowerAction={{
          type: "move_forward",
          quote_id: marcusHale.options[0]!.quote_id,
          message: null,
          at: "2026-09-25T00:00:00Z",
        }}
        onActionTaken={noop}
      />,
    );

    const text = screen.getByTestId("actions-slot").textContent ?? "";
    expect(text).not.toMatch(/\baccept\w*\b/i);
    expect(text).not.toMatch(/\block\b/i);
    expect(text).not.toMatch(/\bapproved rate\b/i);
  });
});
