import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ POST: postMock }),
}));

import { OtpForm } from "./OtpForm";

// The generic form behaviour (digit-stripping, pending state, error
// shapes) is covered by @cq/ui's OtpForm tests. This app only wires it to
// the borrower otp/verify endpoint and its own copy.
describe("OtpForm (Borrower Portal wiring)", () => {
  afterEach(() => {
    postMock.mockReset();
  });

  it("posts to the borrower otp/verify endpoint and calls onSuccess", async () => {
    postMock.mockResolvedValueOnce({
      data: {
        account_id: "a1",
        email: "borrower@clearquote.test",
        client_id: "c1",
        full_name: "Casey Morgan",
        first_name: "Casey",
        latest_application: null,
      },
      error: undefined,
    });
    const onSuccess = vi.fn();
    const user = userEvent.setup();

    render(
      <OtpForm
        challengeId="chal_123"
        email="borrower@clearquote.test"
        onSuccess={onSuccess}
        onBack={vi.fn()}
      />,
    );
    await user.type(screen.getByLabelText("Verification code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith("/api/v1/auth/borrower/otp/verify", {
        body: { challenge_id: "chal_123", code: "123456" },
      }),
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it("shows the Borrower Portal's 'we emailed you a code' copy regardless of new-vs-existing, and 'Use a different email' back label", () => {
    render(
      <OtpForm
        challengeId="chal_123"
        email="borrower@clearquote.test"
        onSuccess={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    expect(
      screen.getByText("We emailed you a code — enter it below. Sent to borrower@clearquote.test."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use a different email" })).toBeInTheDocument();
  });

  it("calls onBack when 'Use a different email' is clicked", async () => {
    const onBack = vi.fn();
    const user = userEvent.setup();

    render(
      <OtpForm
        challengeId="chal_1"
        email="borrower@clearquote.test"
        onSuccess={vi.fn()}
        onBack={onBack}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Use a different email" }));

    expect(onBack).toHaveBeenCalledTimes(1);
    expect(postMock).not.toHaveBeenCalled();
  });
});
