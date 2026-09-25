import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

// `vi.hoisted`: the api-client mock factory runs when `lib/api-client` is
// first imported (hoisted above plain `const`s) -- same convention as
// `features/report/ReportView.test.tsx`.
const { getMock, postMock, replaceMock, pushMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
  replaceMock: vi.fn(),
  pushMock: vi.fn(),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: postMock }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: pushMock }),
  usePathname: () => "/",
}));

import HomePage from "./page";

function ok(data: unknown) {
  return { data, error: undefined, response: { status: 200 } };
}

function failure(status: number) {
  return { data: undefined, error: { error: { code: "X", message: "x" } }, response: { status } };
}

const EMPTY_HOME = {
  first_name: "Casey",
  email: "casey@clearquote-demo.test",
  applications: [] as unknown[],
};

const APPLICATION_BASE = {
  id: "a1111111-1111-1111-1111-111111111111",
  secondary_report_token: null,
  lo: { name: "Taylor Morgan", phone: "8135551234", email: "taylor.morgan@clearquote-demo.test" },
};

describe("(portal) home", () => {
  afterEach(() => {
    getMock.mockReset();
    replaceMock.mockReset();
    pushMock.mockReset();
  });

  it("greets the borrower", async () => {
    getMock.mockResolvedValueOnce(ok(EMPTY_HOME));
    render(<HomePage />);
    expect(await screen.findByRole("heading", { name: "Hi Casey" })).toBeInTheDocument();
  });

  it("shows the empty state and starts the application on click", async () => {
    getMock.mockResolvedValueOnce(ok(EMPTY_HOME));
    render(<HomePage />);

    expect(await screen.findByText("No application yet")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Start your application" });
    await userEvent.click(button);
    expect(pushMock).toHaveBeenCalledWith("/apply");
  });

  it("renders a card with the stage label and a working next-action button (view_report)", async () => {
    getMock.mockResolvedValueOnce(
      ok({
        ...EMPTY_HOME,
        applications: [
          {
            ...APPLICATION_BASE,
            stage: "preapproved",
            label: "Your pre-approval is ready",
            next_action: { type: "view_report", report_token: "tok-123" },
          },
        ],
      }),
    );
    render(<HomePage />);

    expect(await screen.findByText("Your pre-approval is ready")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "See your numbers" });
    await userEvent.click(button);
    expect(pushMock).toHaveBeenCalledWith("/report/tok-123");
  });

  it("option_selected: no primary button, but a secondary 'View your numbers' link", async () => {
    getMock.mockResolvedValueOnce(
      ok({
        ...EMPTY_HOME,
        applications: [
          {
            ...APPLICATION_BASE,
            stage: "option_selected",
            label: "You chose an option — Taylor will be in touch",
            next_action: { type: "none" },
            secondary_report_token: "tok-456",
          },
        ],
      }),
    );
    render(<HomePage />);

    expect(
      await screen.findByText("You chose an option — Taylor will be in touch"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View your numbers" })).toHaveAttribute(
      "href",
      "/report/tok-456",
    );
  });

  it("shows a task banner when an application has a pending credit-check consent", async () => {
    getMock.mockResolvedValueOnce(
      ok({
        ...EMPTY_HOME,
        applications: [
          {
            ...APPLICATION_BASE,
            stage: "in_review",
            label: "Your loan officer is reviewing your numbers",
            next_action: {
              type: "authorize_credit_check",
              consent_id: "c1111111-1111-1111-1111-111111111111",
            },
          },
        ],
      }),
    );
    render(<HomePage />);

    await waitFor(() => expect(getMock).toHaveBeenCalled());
    expect(
      await screen.findByText("Your loan officer needs your permission for a credit check."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review and authorize" })).toHaveAttribute(
      "href",
      "/tasks/credit-check/c1111111-1111-1111-1111-111111111111",
    );
  });

  it("clears the stale session and redirects to login on a 401", async () => {
    getMock.mockResolvedValueOnce(failure(401));
    render(<HomePage />);
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
    expect(postMock).toHaveBeenCalledWith("/api/v1/auth/borrower/logout");
  });
});
