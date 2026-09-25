import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ POST: postMock }),
}));

import { SignupForm } from "./SignupForm";

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Full name"), "Casey Morgan");
  await user.type(screen.getByLabelText("Email"), "casey@clearquote.test");
  await user.type(screen.getByLabelText("Password"), "hunter22");
  await user.type(screen.getByLabelText("Confirm password"), "hunter22");
}

describe("SignupForm", () => {
  afterEach(() => {
    postMock.mockReset();
  });

  it("submits full name, email and password and calls onChallenge with the challenge id and email", async () => {
    postMock.mockResolvedValueOnce({
      data: { challenge_id: "chal_123" },
      error: undefined,
    });
    const onChallenge = vi.fn();
    const user = userEvent.setup();

    render(<SignupForm onChallenge={onChallenge} />);
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith("/api/v1/auth/borrower/signup", {
        body: {
          full_name: "Casey Morgan",
          email: "casey@clearquote.test",
          password: "hunter22",
        },
      }),
    );
    expect(onChallenge).toHaveBeenCalledWith("chal_123", "casey@clearquote.test");
  });

  it("blocks the submit and shows an error when the passwords do not match", async () => {
    const onChallenge = vi.fn();
    const user = userEvent.setup();

    render(<SignupForm onChallenge={onChallenge} />);
    await user.type(screen.getByLabelText("Full name"), "Casey Morgan");
    await user.type(screen.getByLabelText("Email"), "casey@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "hunter22");
    await user.type(screen.getByLabelText("Confirm password"), "different1");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Passwords do not match");
    expect(postMock).not.toHaveBeenCalled();
    expect(onChallenge).not.toHaveBeenCalled();
  });

  it("blocks the submit and shows an error when the password is shorter than 8 characters", async () => {
    const user = userEvent.setup();

    render(<SignupForm onChallenge={vi.fn()} />);
    await user.type(screen.getByLabelText("Full name"), "Casey Morgan");
    await user.type(screen.getByLabelText("Email"), "casey@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "short1");
    await user.type(screen.getByLabelText("Confirm password"), "short1");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Password must be at least 8 characters",
    );
    expect(postMock).not.toHaveBeenCalled();
  });

  it("blocks the submit and shows an error when full name is blank/whitespace-only, without a round trip", async () => {
    const user = userEvent.setup();

    render(<SignupForm onChallenge={vi.fn()} />);
    await user.type(screen.getByLabelText("Full name"), "   ");
    await user.type(screen.getByLabelText("Email"), "casey@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "hunter22");
    await user.type(screen.getByLabelText("Confirm password"), "hunter22");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Full name must be between 1 and 200",
    );
    expect(postMock).not.toHaveBeenCalled();
  });

  it("submits the trimmed full name, not the raw value", async () => {
    postMock.mockResolvedValueOnce({ data: { challenge_id: "chal_123" }, error: undefined });
    const user = userEvent.setup();

    render(<SignupForm onChallenge={vi.fn()} />);
    await user.type(screen.getByLabelText("Full name"), "  Casey Morgan  ");
    await user.type(screen.getByLabelText("Email"), "casey@clearquote.test");
    await user.type(screen.getByLabelText("Password"), "hunter22");
    await user.type(screen.getByLabelText("Confirm password"), "hunter22");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith(
        "/api/v1/auth/borrower/signup",
        expect.objectContaining({ body: expect.objectContaining({ full_name: "Casey Morgan" }) }),
      ),
    );
  });

  it("shows the backend's 409 message when there is no loan officer to assign", async () => {
    postMock.mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "NO_LOAN_OFFICER", message: "No loan officer is available." } },
    });
    const user = userEvent.setup();

    render(<SignupForm onChallenge={vi.fn()} />);
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No loan officer is available.");
  });

  it("shows the backend's 429 message", async () => {
    postMock.mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "RATE_LIMITED", message: "Too many attempts. Try again later." } },
    });
    const user = userEvent.setup();

    render(<SignupForm onChallenge={vi.fn()} />);
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many attempts. Try again later.",
    );
  });

  // The bug this covers: FastAPI's own request-validation 422 body is
  // `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`, not the
  // app's `{"error": {...}}` envelope. Before the fix, this fell straight
  // through to the generic fallback instead of showing the backend's
  // actual validator message — e.g. a server-side rule the client-side
  // checks above don't replicate.
  it("surfaces a FastAPI 422 validation message, not the generic fallback", async () => {
    postMock.mockResolvedValueOnce({
      data: undefined,
      error: {
        detail: [
          {
            loc: ["body", "full_name"],
            msg: "Value error, must not contain profanity",
            type: "value_error",
          },
        ],
      },
    });
    const user = userEvent.setup();

    render(<SignupForm onChallenge={vi.fn()} />);
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("must not contain profanity");
    expect(alert).not.toHaveTextContent("Something went wrong");
  });

  it("disables the submit button while the request is pending", async () => {
    let resolveRequest: (value: unknown) => void = () => {};
    postMock.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveRequest = resolve;
      }),
    );
    const user = userEvent.setup();

    render(<SignupForm onChallenge={vi.fn()} />);
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create account" })).toBeDisabled(),
    );

    resolveRequest({ data: { challenge_id: "chal_1" }, error: undefined });
  });
});
