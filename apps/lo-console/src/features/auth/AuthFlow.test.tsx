import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { postMock, replaceMock } = vi.hoisted(() => ({
  postMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ POST: postMock }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

import { AuthFlow } from "./AuthFlow";

describe("AuthFlow", () => {
  afterEach(() => {
    postMock.mockReset();
    replaceMock.mockReset();
  });

  it("moves from the login step to the OTP step on a successful login, then to / on a successful verify", async () => {
    postMock
      .mockResolvedValueOnce({ data: { challenge_id: "chal_123" }, error: undefined })
      .mockResolvedValueOnce({
        data: { id: "u1", email: "lo@clearquote.test", full_name: "Jamie Rivera", role: "lo" },
        error: undefined,
      });
    const user = userEvent.setup();

    render(<AuthFlow />);

    await user.type(screen.getByLabelText("Email"), "lo@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "hunter2");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByLabelText("Verification code")).toBeInTheDocument();
    expect(
      screen.getByText("Enter the 6-digit code sent to lo@clearquote.test."),
    ).toBeInTheDocument();

    await user.type(screen.getByLabelText("Verification code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/"));
  });

  it("'Use a different account' returns to the login step", async () => {
    postMock.mockResolvedValueOnce({ data: { challenge_id: "chal_123" }, error: undefined });
    const user = userEvent.setup();

    render(<AuthFlow />);
    await user.type(screen.getByLabelText("Email"), "lo@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "hunter2");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await screen.findByLabelText("Verification code");
    await user.click(screen.getByRole("button", { name: "Use a different account" }));

    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
    expect(screen.queryByLabelText("Verification code")).not.toBeInTheDocument();
  });
});
