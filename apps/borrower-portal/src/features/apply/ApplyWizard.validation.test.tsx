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

  // CQ-032b review round 1 (stage-6 major): switching tabs used to remount
  // `ActiveTabPane` (`key={activeTab}`) without flushing whatever edit was
  // still mid-debounce, so a quick "type, then leave the tab within 1 s"
  // silently dropped it. `onBack`/`goToTab` now await the active pane's
  // own `saveNow()` (via `registerSaveNow`) before switching, the same
  // flush "Next" already did locally.
  it("Back within 1s flushes the pending edit before switching tabs", async () => {
    postMock.mockResolvedValueOnce({
      data: draft({
        current_tab: "income",
        data: {
          you: { first_name: "Tina", last_name: "Tampa" },
          property: { occupancy: "primary" },
          income: { liquid_assets: "1000" },
        },
      }),
    });
    getMock.mockResolvedValueOnce({ data: METROS });
    patchMock.mockResolvedValueOnce({
      data: {
        draft: draft({ current_tab: "income" }),
        tab: "income",
        tab_valid: false,
        field_errors: {},
      },
    });

    render(<ApplyWizard />);
    await mountReady();

    expect(screen.getByRole("heading", { name: "Income" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Liquid assets"), { target: { value: "5000" } });
    // Click Back well before the 1 s autosave debounce would have fired on
    // its own.
    fireEvent.click(screen.getByRole("button", { name: "Back" }));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(patchMock).toHaveBeenCalledTimes(1);
    const [, patchInit] = patchMock.mock.calls[0] as [
      unknown,
      { body: { tab: string; data: unknown } },
    ];
    expect(patchInit.body).toMatchObject({ tab: "income", data: { liquid_assets: "5000" } });
    // The flush resolved, so Back actually switched tabs.
    expect(screen.getByLabelText("What's this loan for?")).toBeInTheDocument();
  });

  it("a Stepper click within 1s flushes the pending edit before switching tabs", async () => {
    postMock.mockResolvedValueOnce({
      data: draft({
        current_tab: "income",
        data: {
          you: { first_name: "Tina", last_name: "Tampa" },
          property: { occupancy: "primary" },
          income: { liquid_assets: "1000" },
        },
      }),
    });
    getMock.mockResolvedValueOnce({ data: METROS });
    patchMock.mockResolvedValueOnce({
      data: {
        draft: draft({ current_tab: "income" }),
        tab: "income",
        tab_valid: false,
        field_errors: {},
      },
    });

    render(<ApplyWizard />);
    await mountReady();

    fireEvent.change(screen.getByLabelText("Liquid assets"), { target: { value: "7500" } });
    // "You" (tab 1) is unlocked (current_tab is "income", tab 3) -- click
    // it well before the 1 s debounce would have fired on its own.
    fireEvent.click(screen.getByRole("button", { name: "You" }));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(patchMock).toHaveBeenCalledTimes(1);
    const [, patchInit] = patchMock.mock.calls[0] as [
      unknown,
      { body: { tab: string; data: unknown } },
    ];
    expect(patchInit.body).toMatchObject({ tab: "income", data: { liquid_assets: "7500" } });
    expect(screen.getByRole("heading", { name: "You" })).toBeInTheDocument();
  });

  // CQ-032b review round 1 (minor): a double-click on Next/Submit used to
  // be able to fire `saveNow()`/submit twice.
  it("disables Next while its own saveNow/advance round trip is in flight", async () => {
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

    const nextButton = screen.getByRole("button", { name: "Next" });
    fireEvent.click(nextButton);
    // Fired back-to-back, before the first click's save round trip
    // resolves: the button should already be disabled.
    fireEvent.click(nextButton);

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(patchMock).toHaveBeenCalledTimes(1);
  });

  // CQ-032b review round 1 (code review on the first fix): the Next/Submit
  // guard above didn't cover Back or the Stepper, which also flush via the
  // newly-async `onBack`/`goToTab` -- a double-click on either could fire
  // two concurrent saves. Fixed two ways: `ApplyWizard` disables Back/the
  // Stepper for the duration of its own flush, and `useTabAutosave`'s
  // `saveNow` is re-entrant-safe (a second call while one's in flight gets
  // the same in-flight promise). This test would catch a regression in
  // either.
  it("disables Back while flushing, so a double-click can't fire two saves", async () => {
    postMock.mockResolvedValueOnce({
      data: draft({ current_tab: "income", data: { property: { occupancy: "primary" } } }),
    });
    getMock.mockResolvedValueOnce({ data: METROS });
    patchMock.mockResolvedValueOnce({
      data: {
        draft: draft({ current_tab: "income" }),
        tab: "income",
        tab_valid: false,
        field_errors: {},
      },
    });

    render(<ApplyWizard />);
    await mountReady();

    const backButton = screen.getByRole("button", { name: "Back" });
    fireEvent.click(backButton);
    // Fired before the first click's flush resolves: Back should already
    // be disabled.
    fireEvent.click(backButton);

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(patchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("What's this loan for?")).toBeInTheDocument();
  });

  it("disables the Stepper while flushing, so a double-click can't fire two saves", async () => {
    postMock.mockResolvedValueOnce({
      data: draft({ current_tab: "income", data: { you: { first_name: "T" } } }),
    });
    getMock.mockResolvedValueOnce({ data: METROS });
    patchMock.mockResolvedValueOnce({
      data: {
        draft: draft({ current_tab: "income" }),
        tab: "income",
        tab_valid: false,
        field_errors: {},
      },
    });

    render(<ApplyWizard />);
    await mountReady();

    const youButton = screen.getByRole("button", { name: "You" });
    fireEvent.click(youButton);
    fireEvent.click(youButton);

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(patchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("heading", { name: "You" })).toBeInTheDocument();
  });
});
