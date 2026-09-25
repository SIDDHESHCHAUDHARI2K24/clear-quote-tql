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
// the staff otp/verify endpoint and its own copy.
describe("OtpForm (LO Console wiring)", () => {
  afterEach(() => {
    postMock.mockReset();
  });

  it("posts to the staff otp/verify endpoint and calls onSuccess", async () => {
    postMock.mockResolvedValueOnce({
      data: { id: "u1", email: "lo@clearquote.test", full_name: "Jamie Rivera", role: "lo" },
      error: undefined,
    });
    const onSuccess = vi.fn();
    const user = userEvent.setup();

    render(
      <OtpForm
        challengeId="chal_123"
        email="lo@clearquote.test"
        onSuccess={onSuccess}
        onBack={vi.fn()}
      />,
    );
    await user.type(screen.getByLabelText("Verification code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith("/api/v1/auth/staff/otp/verify", {
        body: { challenge_id: "chal_123", code: "123456" },
      }),
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it("shows the LO Console's 'sent to {email}' copy and 'Use a different account' back label", () => {
    render(
      <OtpForm
        challengeId="chal_1"
        email="lo@clearquote.test"
        onSuccess={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    expect(
      screen.getByText("Enter the 6-digit code sent to lo@clearquote.test."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use a different account" })).toBeInTheDocument();
  });

  it("calls onBack when 'Use a different account' is clicked", async () => {
    const onBack = vi.fn();
    const user = userEvent.setup();

    render(
      <OtpForm
        challengeId="chal_1"
        email="lo@clearquote.test"
        onSuccess={vi.fn()}
        onBack={onBack}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Use a different account" }));

    expect(onBack).toHaveBeenCalledTimes(1);
    expect(postMock).not.toHaveBeenCalled();
  });
});
