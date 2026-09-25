import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Same technique as `SupportForm.test.tsx`/`WorkspaceProvider.test.tsx`:
// mock the generated client's HTTP verbs, then chain `mockResolvedValueOnce`
// per call in the order the wizard makes them.
const { getMock, postMock, patchMock, deleteMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  patchMock: vi.fn(),
  deleteMock: vi.fn(),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: postMock, PATCH: patchMock, DELETE: deleteMock }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

import { ApplyWizard } from "./ApplyWizard";

const CONSENT = { version: "apply-v1", text: "By continuing you agree to..." };
const METROS = { states: [{ state: "FL", metros: ["Tampa", "Davenport"] }] };

function draft(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "d1111111-1111-1111-1111-111111111111",
    email: "tina@example.com",
    current_tab: "you",
    tabs: {
      you: { complete: false },
      property: { complete: false },
      income: { complete: false },
      consent: { complete: false },
    },
    data: {},
    submitted_application_id: null,
    consent: CONSENT,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

async function mountReady() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("ApplyWizard", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    patchMock.mockReset();
    deleteMock.mockReset();
    vi.useRealTimers();
  });

  it("resumes at the server's current_tab (AC3)", async () => {
    postMock.mockResolvedValueOnce({
      data: draft({
        current_tab: "income",
        data: {
          you: { first_name: "Tina", last_name: "Tampa" },
          property: { occupancy: "str" },
          income: { liquid_assets: "1000" },
        },
      }),
    });
    getMock.mockResolvedValueOnce({ data: METROS });

    render(<ApplyWizard />);
    await mountReady();

    expect(screen.getByRole("heading", { name: "Income" })).toBeInTheDocument();
    expect(screen.getByLabelText("Liquid assets")).toHaveValue("1000");
  });

  it("Next on an invalid tab shows field errors and does not advance", async () => {
    postMock.mockResolvedValueOnce({ data: draft() });
    getMock.mockResolvedValueOnce({ data: METROS });
    patchMock.mockResolvedValueOnce({
      data: {
        draft: draft(),
        tab: "you",
        tab_valid: false,
        field_errors: { first_name: "This field is required." },
      },
    });

    render(<ApplyWizard />);
    await mountReady();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(patchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText("This field is required.")).toBeInTheDocument();
    // Still on tab 1: tab 2's own heading never rendered.
    expect(screen.queryByText("What's this loan for?")).not.toBeInTheDocument();
  });

  it("Next on a valid tab advances to the next tab", async () => {
    postMock.mockResolvedValueOnce({ data: draft() });
    getMock.mockResolvedValueOnce({ data: METROS });
    patchMock.mockResolvedValueOnce({
      data: {
        draft: draft({ current_tab: "property" }),
        tab: "you",
        tab_valid: true,
        field_errors: {},
      },
    });

    render(<ApplyWizard />);
    await mountReady();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByLabelText("What's this loan for?")).toBeInTheDocument();
  });

  it("autosaves 1s after the last change and shows Saved", async () => {
    postMock.mockResolvedValueOnce({ data: draft() });
    getMock.mockResolvedValueOnce({ data: METROS });
    patchMock.mockResolvedValueOnce({
      data: { draft: draft(), tab: "you", tab_valid: false, field_errors: {} },
    });

    render(<ApplyWizard />);
    await mountReady();

    fireEvent.change(screen.getByLabelText("First name"), { target: { value: "Tina" } });
    expect(patchMock).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(patchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("submitting on the consent tab shows the confirmation screen (AC1 shape)", async () => {
    postMock
      .mockResolvedValueOnce({
        data: draft({
          current_tab: "consent",
          tabs: {
            you: { complete: true },
            property: { complete: true },
            income: { complete: true },
            consent: { complete: false },
          },
          data: {
            you: { first_name: "Tina", last_name: "Tampa" },
            property: { occupancy: "str" },
            income: { liquid_assets: "1000" },
            consent: {},
          },
        }),
      })
      .mockResolvedValueOnce({
        data: {
          application_id: "a1111111-1111-1111-1111-111111111111",
          draft_id: "d1111111-1111-1111-1111-111111111111",
          status: "intake",
          assigned_lo_name: "Lena LO",
          pipeline_started: true,
        },
      });
    getMock.mockResolvedValueOnce({ data: METROS });
    patchMock.mockResolvedValueOnce({
      data: {
        draft: draft({ current_tab: "consent" }),
        tab: "consent",
        tab_valid: true,
        field_errors: {},
      },
    });

    render(<ApplyWizard />);
    await mountReady();

    fireEvent.click(screen.getByRole("button", { name: "Submit application" }));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByRole("heading", { name: "Application submitted" })).toBeInTheDocument();
    expect(screen.getByText(/Lena LO/)).toBeInTheDocument();
  });
});
