import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ POST: postMock }),
}));

import { OtpForm } from "./OtpForm";

describe("OtpForm", () => {
  afterEach(() => {
    postMock.mockReset();
  });

  it("submits the 6-digit code and calls onSuccess", async () => {
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

  it("strips non-digit characters and caps input at 6 characters", async () => {
    const user = userEvent.setup();
    render(
      <OtpForm
        challengeId="chal_1"
        email="lo@clearquote.test"
        onSuccess={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    const input = screen.getByLabelText("Verification code");
    await user.type(input, "12a3b456789");

    expect(input).toHaveValue("123456");
  });

  it("shows the backend's message on an invalid/expired code and does not call onSuccess", async () => {
    postMock.mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "AUTHENTICATION_ERROR", message: "Invalid or expired code" } },
    });
    const onSuccess = vi.fn();
    const user = userEvent.setup();

    render(
      <OtpForm
        challengeId="chal_1"
        email="lo@clearquote.test"
        onSuccess={onSuccess}
        onBack={vi.fn()}
      />,
    );
    await user.type(screen.getByLabelText("Verification code"), "000000");
    await user.click(screen.getByRole("button", { name: "Verify" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid or expired code");
    expect(onSuccess).not.toHaveBeenCalled();
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
