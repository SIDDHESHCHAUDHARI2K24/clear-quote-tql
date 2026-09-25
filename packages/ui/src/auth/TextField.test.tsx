import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TextField } from "./TextField";

describe("TextField", () => {
  it("associates the label with the input and forwards standard input props", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(
      <TextField
        id="email"
        label="Email"
        type="email"
        autoComplete="username"
        required
        value=""
        onChange={onChange}
      />,
    );

    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("type", "email");
    expect(input).toHaveAttribute("autoComplete", "username");
    expect(input).toBeRequired();

    await user.type(input, "a");
    expect(onChange).toHaveBeenCalled();
  });

  it("disables the input when disabled is passed", () => {
    render(<TextField id="otp" label="Verification code" value="" disabled onChange={vi.fn()} />);
    expect(screen.getByLabelText("Verification code")).toBeDisabled();
  });

  it("renders helper text under the input when provided", () => {
    render(
      <TextField
        id="password"
        label="Password"
        value=""
        onChange={vi.fn()}
        helperText="At least 8 characters."
      />,
    );
    expect(screen.getByText("At least 8 characters.")).toBeInTheDocument();
  });

  it("keeps the shared input inputMode/autoComplete/maxLength props for the OTP use case", () => {
    render(
      <TextField
        id="otp-code"
        label="Verification code"
        type="text"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        value=""
        onChange={vi.fn()}
      />,
    );

    const input = screen.getByLabelText("Verification code");
    expect(input).toHaveAttribute("inputMode", "numeric");
    expect(input).toHaveAttribute("autoComplete", "one-time-code");
    expect(input).toHaveAttribute("maxLength", "6");
  });
});
