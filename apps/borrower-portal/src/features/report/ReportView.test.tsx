import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { REPORT_FIXTURES } from "@cq/ui";

const { getMock, postMock, replaceMock, searchParamsGet } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  replaceMock: vi.fn(),
  searchParamsGet: vi.fn(() => null),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: postMock }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  useSearchParams: () => ({ get: searchParamsGet, toString: () => "" }),
}));

import { ReportView } from "./ReportView";

const marcusHale = REPORT_FIXTURES.find((f) => f.key === "marcus_hale")!.viewModel;

function ok(data: unknown) {
  return { data, error: undefined, response: { status: 200 } };
}

function failure(status: number) {
  return { data: undefined, error: { error: { code: "X", message: "x" } }, response: { status } };
}

describe("ReportView", () => {
  afterEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    replaceMock.mockReset();
    searchParamsGet.mockReset();
    searchParamsGet.mockReturnValue(null);
  });

  it("shows a loading state before the fetch resolves", () => {
    getMock.mockReturnValue(new Promise(() => {})); // never resolves
    render(<ReportView token="tok_abc" />);

    expect(screen.getByText(/Loading your report/i)).toBeInTheDocument();
  });

  it("renders the report once loaded", async () => {
    getMock.mockResolvedValueOnce(ok({ ...marcusHale, borrower_action: null }));
    render(<ReportView token="tok_abc" />);

    expect(await screen.findByText(/here are your numbers/i)).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith(
      "/api/v1/portal/reports/{token}",
      expect.objectContaining({ params: { path: { token: "tok_abc" } } }),
    );
  });

  it("shows a friendly not-found message on 404 (spec.md AC5)", async () => {
    getMock.mockResolvedValueOnce(failure(404));
    render(<ReportView token="tok_random" />);

    expect(await screen.findByText(/couldn.t find that report/i)).toBeInTheDocument();
  });

  it("logs out and redirects to /login?next=... on 401 (a stale session)", async () => {
    getMock.mockResolvedValueOnce(failure(401));
    postMock.mockResolvedValueOnce({ data: undefined, error: undefined });
    render(<ReportView token="tok_abc" />);

    await waitFor(() =>
      expect(replaceMock).toHaveBeenCalledWith(
        `/login?next=${encodeURIComponent("/report/tok_abc")}`,
      ),
    );
  });

  it("shows a generic error message when the request itself fails", async () => {
    getMock.mockRejectedValueOnce(new Error("network down"));
    render(<ReportView token="tok_abc" />);

    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
  });

  it("shows the generic error message (not 'not found') on a transient 5xx (fresh-review finding)", async () => {
    getMock.mockResolvedValueOnce(failure(500));
    render(<ReportView token="tok_abc" />);

    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
    expect(screen.queryByText(/couldn.t find that report/i)).not.toBeInTheDocument();
  });

  it("passes newest_report_token through as the superseded banner's link", async () => {
    const superseded = REPORT_FIXTURES.find((f) => f.key === "priya_nair_superseded")!.viewModel;
    getMock.mockResolvedValueOnce(
      ok({ ...superseded, borrower_action: null, newest_report_token: "tok_newest" }),
    );
    render(<ReportView token="tok_old" />);

    const link = await screen.findByRole("link", { name: "Open your most recent report" });
    expect(link).toHaveAttribute("href", "/report/tok_newest");
  });

  it("updates the URL with ?option= when the switcher changes (AC3)", async () => {
    getMock.mockResolvedValueOnce(ok({ ...marcusHale, borrower_action: null }));
    const user = userEvent.setup();
    render(<ReportView token="tok_abc" />);

    await screen.findByText(/here are your numbers/i);
    const buydown = marcusHale.options.find((o) => !o.recommended)!;
    await user.click(screen.getByRole("radio", { name: new RegExp(buydown.label) }));

    expect(replaceMock).toHaveBeenCalledWith(
      expect.stringContaining(`/report/tok_abc?option=${buydown.quote_id}`),
      { scroll: false },
    );
  });
});
