import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CredentialsForm } from "./CredentialsForm";
import type { AsyncSubmitResult } from "./useAsyncSubmit";

describe("CredentialsForm", () => {
  it("submits email and password and calls onSuccess with the response data and the entered values", async () => {
    const onSubmit = vi.fn().mockResolvedValue({ ok: true, data: { challenge_id: "chal_123" } });
    const onSuccess = vi.fn();
    const user = userEvent.setup();

    render(<CredentialsForm submitLabel="Sign in" onSubmit={onSubmit} onSuccess={onSuccess} />);
    await user.type(screen.getByLabelText("Email"), "lo@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "hunter2");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({ email: "lo@clearquote.test", password: "hunter2" }),
    );
    expect(onSuccess).toHaveBeenCalledWith(
      { challenge_id: "chal_123" },
      { email: "lo@clearquote.test", password: "hunter2" },
    );
  });

  it("shows the app error envelope's message on failure and does not call onSuccess", async () => {
    const onSubmit = vi.fn().mockResolvedValue({
      ok: false,
      error: { error: { code: "AUTHENTICATION_ERROR", message: "Invalid email or password" } },
    });
    const onSuccess = vi.fn();
    const user = userEvent.setup();

    render(<CredentialsForm submitLabel="Sign in" onSubmit={onSubmit} onSuccess={onSuccess} />);
    await user.type(screen.getByLabelText("Email"), "lo@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("shows a FastAPI 422 validation message when the error is a detail array", async () => {
    const onSubmit = vi.fn().mockResolvedValue({
      ok: false,
      error: {
        detail: [
          {
            loc: ["body", "email"],
            msg: "value is not a valid email address",
            type: "value_error",
          },
        ],
      },
    });
    const user = userEvent.setup();

    render(<CredentialsForm submitLabel="Sign in" onSubmit={onSubmit} onSuccess={vi.fn()} />);
    await user.type(screen.getByLabelText("Email"), "not-an-email");
    await user.type(screen.getByLabelText("Password"), "hunter2");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "value is not a valid email address",
    );
  });

  it("disables the submit button while the request is pending", async () => {
    let resolveRequest: (value: AsyncSubmitResult<{ challenge_id: string }>) => void = () => {};
    const onSubmit = vi.fn(
      () =>
        new Promise<AsyncSubmitResult<{ challenge_id: string }>>((resolve) => {
          resolveRequest = resolve;
        }),
    );
    const user = userEvent.setup();

    render(<CredentialsForm submitLabel="Sign in" onSubmit={onSubmit} onSuccess={vi.fn()} />);
    await user.type(screen.getByLabelText("Email"), "lo@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "hunter2");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled());

    resolveRequest({ ok: true, data: { challenge_id: "chal_1" } });
  });

  it("uses the passwordAutoComplete prop (new-password for sign-up-style callers)", () => {
    render(
      <CredentialsForm
        submitLabel="Sign in"
        onSubmit={vi.fn()}
        onSuccess={vi.fn()}
        passwordAutoComplete="new-password"
      />,
    );

    expect(screen.getByLabelText("Password")).toHaveAttribute("autoComplete", "new-password");
  });
});
