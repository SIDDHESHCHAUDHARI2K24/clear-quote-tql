import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({
    GET: vi.fn(),
    PUT: vi.fn(),
    POST: postMock,
    PATCH: vi.fn(),
    DELETE: vi.fn(),
  }),
}));

import type { SectionField } from "../shared";
import { SsnField } from "./SsnField";

const APPLICATION_ID = "11111111-1111-1111-1111-111111111111";
const PARTY_ID = "party-borrower-1";

function makeField(overrides: Partial<SectionField> = {}): SectionField {
  return {
    field_key: "borrower_ssn",
    label: "SSN",
    value: "***-**-1234",
    source: "encompass",
    overridden: false,
    editable: true,
    ...overrides,
  };
}

// AC7 (docs/backlog/CQ-028-verification-tabs/spec.md): "revealing an SSN
// writes an event and re-masks after 10 s". The backend writes the
// activity event server-side inside POST .../ssn-reveal; this test covers
// the client's half -- showing the raw digits after a successful reveal,
// then automatically re-masking exactly 10s later.
describe("SsnField reveal + re-mask (spec.md AC7)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    postMock.mockReset();
    vi.useRealTimers();
  });

  it("reveals the raw SSN on click, then re-masks after 10s", async () => {
    postMock.mockResolvedValue({ data: { party_id: PARTY_ID, ssn: "123456789" } });

    render(
      <SsnField
        applicationId={APPLICATION_ID}
        partyId={PARTY_ID}
        field={makeField()}
        applyResult={vi.fn()}
      />,
    );

    expect(screen.getByText("***-**-1234")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Reveal" }));
      await Promise.resolve();
    });

    expect(screen.getByText("123-45-6789")).toBeInTheDocument();
    expect(screen.queryByText("***-**-1234")).not.toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(10000);
    });

    expect(screen.getByText("***-**-1234")).toBeInTheDocument();
    expect(screen.queryByText("123-45-6789")).not.toBeInTheDocument();
  });

  it("shows an error message and stays masked when reveal fails", async () => {
    postMock.mockResolvedValue({ data: undefined, error: { error: { message: "Not allowed" } } });

    render(
      <SsnField
        applicationId={APPLICATION_ID}
        partyId={PARTY_ID}
        field={makeField()}
        applyResult={vi.fn()}
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Reveal" }));
      await Promise.resolve();
    });

    expect(screen.getByText("Not allowed")).toBeInTheDocument();
    expect(screen.getByText("***-**-1234")).toBeInTheDocument();
  });

  it("disables Reveal when the party id is unknown", () => {
    render(
      <SsnField
        applicationId={APPLICATION_ID}
        partyId={null}
        field={makeField()}
        applyResult={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Reveal" })).toBeDisabled();
  });
});
