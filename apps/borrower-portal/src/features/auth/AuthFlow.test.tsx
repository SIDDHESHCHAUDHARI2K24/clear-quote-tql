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

const BORROWER_ME = {
  account_id: "a1",
  email: "borrower@clearquote.test",
  client_id: "c1",
  full_name: "Casey Morgan",
  first_name: "Casey",
  latest_application: null,
};

import { AuthFlow } from "./AuthFlow";

describe("AuthFlow", () => {
  afterEach(() => {
    postMock.mockReset();
    replaceMock.mockReset();
  });

  describe("mode='login'", () => {
    it("moves from the login step to the OTP step on a successful login, then to / on a successful verify", async () => {
      postMock
        .mockResolvedValueOnce({ data: { challenge_id: "chal_123" }, error: undefined })
        .mockResolvedValueOnce({ data: BORROWER_ME, error: undefined });
      const user = userEvent.setup();

      render(<AuthFlow mode="login" />);

      await user.type(screen.getByLabelText("Email"), "borrower@clearquote.test");
      await user.type(screen.getByLabelText("Password"), "hunter22");
      await user.click(screen.getByRole("button", { name: "Sign in" }));

      expect(await screen.findByLabelText("Verification code")).toBeInTheDocument();

      await user.type(screen.getByLabelText("Verification code"), "123456");
      await user.click(screen.getByRole("button", { name: "Verify" }));

      await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/"));
    });

    it("shows a 'New here? Create an account' link to /signup", () => {
      render(<AuthFlow mode="login" />);

      const link = screen.getByRole("link", { name: "Create an account" });
      expect(link).toHaveAttribute("href", "/signup");
      expect(screen.getByText(/New here\?/)).toBeInTheDocument();
    });

    it("'Use a different email' returns to the login step", async () => {
      postMock.mockResolvedValueOnce({ data: { challenge_id: "chal_123" }, error: undefined });
      const user = userEvent.setup();

      render(<AuthFlow mode="login" />);
      await user.type(screen.getByLabelText("Email"), "borrower@clearquote.test");
      await user.type(screen.getByLabelText("Password"), "hunter22");
      await user.click(screen.getByRole("button", { name: "Sign in" }));

      await screen.findByLabelText("Verification code");
      await user.click(screen.getByRole("button", { name: "Use a different email" }));

      expect(await screen.findByLabelText("Email")).toBeInTheDocument();
      expect(screen.queryByLabelText("Verification code")).not.toBeInTheDocument();
    });
  });

  describe("mode='signup'", () => {
    it("moves from the signup step to the OTP step on a successful signup, then to / on a successful verify", async () => {
      postMock
        .mockResolvedValueOnce({ data: { challenge_id: "chal_456" }, error: undefined })
        .mockResolvedValueOnce({ data: BORROWER_ME, error: undefined });
      const user = userEvent.setup();

      render(<AuthFlow mode="signup" />);

      await user.type(screen.getByLabelText("Full name"), "Casey Morgan");
      await user.type(screen.getByLabelText("Email"), "casey@clearquote.test");
      await user.type(screen.getByLabelText("Password"), "hunter22");
      await user.type(screen.getByLabelText("Confirm password"), "hunter22");
      await user.click(screen.getByRole("button", { name: "Create account" }));

      expect(await screen.findByLabelText("Verification code")).toBeInTheDocument();

      await user.type(screen.getByLabelText("Verification code"), "123456");
      await user.click(screen.getByRole("button", { name: "Verify" }));

      await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/"));
    });

    it("shows an 'Already have an account? Sign in' link to /login", () => {
      render(<AuthFlow mode="signup" />);

      const link = screen.getByRole("link", { name: "Sign in" });
      expect(link).toHaveAttribute("href", "/login");
      expect(screen.getByText(/Already have an account\?/)).toBeInTheDocument();
    });
  });
});
