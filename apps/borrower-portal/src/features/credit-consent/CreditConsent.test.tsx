import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, postMock, replaceMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: postMock }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  usePathname: () => "/tasks/credit-check/c1",
}));

import type { PortalConsent } from "./api";
import { CreditConsent } from "./CreditConsent";

const CONSENT_ID = "33333333-3333-3333-3333-333333333333";

const PENDING: PortalConsent = {
  id: CONSENT_ID,
  application_id: "44444444-4444-4444-4444-444444444444",
  status: "pending",
  requested_at: "2026-09-20T12:00:00Z",
  expires_at: "2026-10-04T12:00:00Z",
  decided_at: null,
  decline_reason: null,
  borrower_name: "Tom Brandt",
  lo: { name: "Dana Reyes", email: "dana@clearquote-demo.test", phone: null, nmls: null },
  text: {
    version: "hard_pull_v1",
    body: "Who is asking: Clear Quote.\n\nWhich bureaus: Experian, Equifax and TransUnion.",
    sha256: "abc",
  },
  fico_after_pull: null,
};

function ok(data: unknown) {
  return { data, error: undefined, response: { status: 200 } };
}

function fail(status: number, message = "Nope") {
  return {
    data: undefined,
    error: { error: { code: "X", message, details: {} } },
    response: { status },
  };
}

function renderPage(consent: PortalConsent = PENDING) {
  getMock.mockResolvedValueOnce(ok(consent));
  return render(<CreditConsent consentId={CONSENT_ID} />);
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("CreditConsent", () => {
  it("shows the consent text, a labelled checkbox and a labelled name field", async () => {
    renderPage();

    expect(
      await screen.findByRole("heading", { level: 1, name: "Authorize a credit check" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Which bureaus: Experian, Equifax and TransUnion/)).toBeInTheDocument();
    const checkbox = screen.getByRole("checkbox", { name: /I authorize/ });
    expect(checkbox).toBeRequired();
    const name = screen.getByLabelText("Type your full name to sign");
    expect(name).toBeRequired();
    expect(name).toHaveAccessibleDescription(/Tom Brandt/);
  });

  it("requires the checkbox and the typed name, with linked errors (AC7)", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Authorize" }));

    const checkbox = screen.getByRole("checkbox", { name: /I authorize/ });
    expect(checkbox).toHaveAttribute("aria-invalid", "true");
    expect(checkbox).toHaveAccessibleDescription("Check the box to authorize the credit check.");
    expect(checkbox).toHaveFocus();
    expect(postMock).not.toHaveBeenCalled();

    await user.click(checkbox);
    await user.click(screen.getByRole("button", { name: "Authorize" }));

    const name = screen.getByLabelText("Type your full name to sign");
    expect(name).toHaveAttribute("aria-invalid", "true");
    expect(name).toHaveAccessibleDescription(/Type your full name to sign\./);
    expect(name).toHaveFocus();
    expect(postMock).not.toHaveBeenCalled();
  });

  it("authorizes with the typed name and shows the confirmation", async () => {
    const user = userEvent.setup();
    postMock.mockResolvedValueOnce(
      ok({
        ...PENDING,
        status: "accepted",
        decided_at: "2026-09-21T12:00:00Z",
        fico_after_pull: 690,
      }),
    );
    renderPage();

    await user.click(await screen.findByRole("checkbox", { name: /I authorize/ }));
    await user.type(screen.getByLabelText("Type your full name to sign"), "Tom Brandt");
    await user.click(screen.getByRole("button", { name: "Authorize" }));

    expect(postMock).toHaveBeenCalledWith("/api/v1/portal/consents/{consent_id}/accept", {
      params: { path: { consent_id: CONSENT_ID } },
      body: { typed_name: "Tom Brandt" },
    });
    expect(
      await screen.findByRole("heading", { name: "Credit check authorized" }),
    ).toBeInTheDocument();
  });

  it("shows the server's error, e.g. a name mismatch", async () => {
    const user = userEvent.setup();
    postMock.mockResolvedValueOnce(
      fail(422, "The typed name must match your full name on the application."),
    );
    renderPage();

    await user.click(await screen.findByRole("checkbox", { name: /I authorize/ }));
    await user.type(screen.getByLabelText("Type your full name to sign"), "Someone Else");
    await user.click(screen.getByRole("button", { name: "Authorize" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/must match your full name/);
  });

  it("declines with an optional reason after a confirm step", async () => {
    const user = userEvent.setup();
    postMock.mockResolvedValueOnce(
      ok({
        ...PENDING,
        status: "declined",
        decided_at: "2026-09-21T12:00:00Z",
        decline_reason: "Not now",
      }),
    );
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Decline" }));
    await user.type(screen.getByLabelText("Reason for declining (optional)"), "Not now");
    await user.click(screen.getByRole("button", { name: "Confirm decline" }));

    expect(postMock).toHaveBeenCalledWith("/api/v1/portal/consents/{consent_id}/decline", {
      params: { path: { consent_id: CONSENT_ID } },
      body: { reason: "Not now" },
    });
    expect(
      await screen.findByRole("heading", { name: "Credit check declined" }),
    ).toBeInTheDocument();
  });

  it("shows the expired state", async () => {
    renderPage({ ...PENDING, status: "expired" });
    expect(
      await screen.findByRole("heading", { name: "This request has expired" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("sends an expired session to login and back to this request (401)", async () => {
    getMock.mockResolvedValueOnce(fail(401));
    postMock.mockResolvedValueOnce(ok(null));
    render(<CreditConsent consentId={CONSENT_ID} />);
    await vi.waitFor(() =>
      expect(replaceMock).toHaveBeenCalledWith(
        `/login?next=${encodeURIComponent(`/tasks/credit-check/${CONSENT_ID}`)}`,
      ),
    );
  });

  it("shows not found for another borrower's request (404)", async () => {
    getMock.mockResolvedValueOnce(fail(404));
    render(<CreditConsent consentId={CONSENT_ID} />);
    expect(await screen.findByRole("heading", { name: "Request not found" })).toBeInTheDocument();
  });
});
