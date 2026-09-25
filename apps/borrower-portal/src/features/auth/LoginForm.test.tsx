import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ POST: postMock }),
}));

import { LoginForm } from "./LoginForm";

// The generic form behaviour (validation errors, pending state, the
// FastAPI-vs-app error shapes) is covered by @cq/ui's CredentialsForm
// tests. This app only wires it to the borrower login endpoint.
describe("LoginForm (Borrower Portal wiring)", () => {
  afterEach(() => {
    postMock.mockReset();
  });

  it("posts to the borrower login endpoint and calls onChallenge with the challenge id and email", async () => {
    postMock.mockResolvedValueOnce({
      data: { challenge_id: "chal_123" },
      error: undefined,
    });
    const onChallenge = vi.fn();
    const user = userEvent.setup();

    render(<LoginForm onChallenge={onChallenge} />);
    await user.type(screen.getByLabelText("Email"), "borrower@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "hunter22");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith("/api/v1/auth/borrower/login", {
        body: { email: "borrower@clearquote.test", password: "hunter22" },
      }),
    );
    expect(onChallenge).toHaveBeenCalledWith("chal_123", "borrower@clearquote.test");
  });

  it("surfaces the backend's message on a 401 and does not advance", async () => {
    postMock.mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "AUTHENTICATION_ERROR", message: "Invalid email or password" } },
    });
    const onChallenge = vi.fn();
    const user = userEvent.setup();

    render(<LoginForm onChallenge={onChallenge} />);
    await user.type(screen.getByLabelText("Email"), "borrower@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(onChallenge).not.toHaveBeenCalled();
  });

  it("surfaces a FastAPI 422 validation message (not the generic fallback)", async () => {
    postMock.mockResolvedValueOnce({
      data: undefined,
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

    render(<LoginForm onChallenge={vi.fn()} />);
    await user.type(screen.getByLabelText("Email"), "not-an-email");
    await user.type(screen.getByLabelText("Password"), "hunter22");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "value is not a valid email address",
    );
  });
});
