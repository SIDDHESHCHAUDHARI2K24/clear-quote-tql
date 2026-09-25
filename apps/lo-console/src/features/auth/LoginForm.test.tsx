import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ POST: postMock }),
}));

import { LoginForm } from "./LoginForm";

describe("LoginForm", () => {
  afterEach(() => {
    postMock.mockReset();
  });

  it("submits email and password and calls onChallenge with the challenge id and email", async () => {
    postMock.mockResolvedValueOnce({
      data: { challenge_id: "chal_123" },
      error: undefined,
    });
    const onChallenge = vi.fn();
    const user = userEvent.setup();

    render(<LoginForm onChallenge={onChallenge} />);
    await user.type(screen.getByLabelText("Email"), "lo@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "hunter2");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith("/api/v1/auth/staff/login", {
        body: { email: "lo@clearquote.test", password: "hunter2" },
      }),
    );
    expect(onChallenge).toHaveBeenCalledWith("chal_123", "lo@clearquote.test");
  });

  it("shows the backend's message on a 401 and does not advance", async () => {
    postMock.mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "AUTHENTICATION_ERROR", message: "Invalid email or password" } },
    });
    const onChallenge = vi.fn();
    const user = userEvent.setup();

    render(<LoginForm onChallenge={onChallenge} />);
    await user.type(screen.getByLabelText("Email"), "lo@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(onChallenge).not.toHaveBeenCalled();
  });

  it("shows the backend's message on a 429", async () => {
    postMock.mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "RATE_LIMITED", message: "Too many attempts. Try again later." } },
    });
    const user = userEvent.setup();

    render(<LoginForm onChallenge={vi.fn()} />);
    await user.type(screen.getByLabelText("Email"), "lo@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "hunter2");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many attempts. Try again later.",
    );
  });

  it("disables the submit button while the request is pending", async () => {
    let resolveRequest: (value: unknown) => void = () => {};
    postMock.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveRequest = resolve;
      }),
    );
    const user = userEvent.setup();

    render(<LoginForm onChallenge={vi.fn()} />);
    await user.type(screen.getByLabelText("Email"), "lo@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "hunter2");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled());

    resolveRequest({ data: { challenge_id: "chal_1" }, error: undefined });
  });
});
