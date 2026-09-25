import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { OtpForm } from "./OtpForm";

describe("OtpForm", () => {
  it("submits the 6-digit code with the challengeId and calls onSuccess", async () => {
    const onSubmit = vi.fn().mockResolvedValue({ ok: true, data: { id: "u1" } });
    const onSuccess = vi.fn();
    const user = userEvent.setup();

    render(
      <OtpForm
        challengeId="chal_123"
        description="Enter the 6-digit code sent to lo@clearquote.test."
        backLabel="Use a different account"
        onSubmit={onSubmit}
        onSuccess={onSuccess}
        onBack={vi.fn()}
      />,
    );
    await user.type(screen.getByLabelText("Verification code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({ challengeId: "chal_123", code: "123456" }),
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it("renders the caller-provided description", () => {
    render(
      <OtpForm
        challengeId="chal_1"
        description="We emailed you a code — enter it below. Sent to borrower@clearquote.test."
        backLabel="Use a different email"
        onSubmit={vi.fn()}
        onSuccess={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    expect(
      screen.getByText("We emailed you a code — enter it below. Sent to borrower@clearquote.test."),
    ).toBeInTheDocument();
  });

  it("strips non-digit characters and caps input at 6 characters", async () => {
    const user = userEvent.setup();
    render(
      <OtpForm
        challengeId="chal_1"
        description="desc"
        backLabel="Use a different account"
        onSubmit={vi.fn()}
        onSuccess={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    const input = screen.getByLabelText("Verification code");
    await user.type(input, "12a3b456789");

    expect(input).toHaveValue("123456");
  });

  it("shows the backend's message on an invalid/expired code and does not call onSuccess", async () => {
    const onSubmit = vi.fn().mockResolvedValue({
      ok: false,
      error: { error: { code: "AUTHENTICATION_ERROR", message: "Invalid or expired code" } },
    });
    const onSuccess = vi.fn();
    const user = userEvent.setup();

    render(
      <OtpForm
        challengeId="chal_1"
        description="desc"
        backLabel="Use a different account"
        onSubmit={onSubmit}
        onSuccess={onSuccess}
        onBack={vi.fn()}
      />,
    );
    await user.type(screen.getByLabelText("Verification code"), "000000");
    await user.click(screen.getByRole("button", { name: "Verify" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid or expired code");
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("calls onBack with the caller-provided label and does not submit", async () => {
    const onBack = vi.fn();
    const onSubmit = vi.fn();
    const user = userEvent.setup();

    render(
      <OtpForm
        challengeId="chal_1"
        description="desc"
        backLabel="Use a different account"
        onSubmit={onSubmit}
        onSuccess={vi.fn()}
        onBack={onBack}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Use a different account" }));

    expect(onBack).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
