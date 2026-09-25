import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

// `vi.hoisted`: the api-client mock factory runs when `lib/api-client` is
// first imported (hoisted above plain `const`s) -- same technique
// `(portal)/page.test.tsx` uses.
const { getMock, postMock, replaceMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: postMock }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  usePathname: () => "/support",
}));

import { BorrowerSessionProvider } from "../shell";
import type { BorrowerMe } from "../shell";
import { SupportForm } from "./SupportForm";

const BORROWER_ME: BorrowerMe = {
  account_id: "11111111-1111-1111-1111-111111111111",
  email: "marcus.hale@clearquote-demo.test",
  client_id: "22222222-2222-2222-2222-222222222222",
  full_name: "Marcus Hale",
  first_name: "Marcus",
  phone: "8135550100",
  latest_application: null,
};

function renderForm(me: BorrowerMe = BORROWER_ME) {
  getMock.mockResolvedValueOnce({ data: me, error: undefined });
  return render(
    <BorrowerSessionProvider>
      <SupportForm />
    </BorrowerSessionProvider>,
  );
}

async function fillValidMessage(user: ReturnType<typeof userEvent.setup>) {
  const textarea = await screen.findByLabelText("Message");
  await user.type(textarea, "I have a question about the buydown option on my quote.");
  return textarea;
}

describe("SupportForm", () => {
  afterEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    replaceMock.mockReset();
  });

  it("prefills phone from the borrower's /me profile", async () => {
    renderForm();
    expect(await screen.findByRole("textbox", { name: /phone/i })).toHaveValue("8135550100");
  });

  it("shows a character counter for the message", async () => {
    const user = userEvent.setup();
    renderForm();
    const textarea = await fillValidMessage(user);
    expect(textarea).toHaveValue("I have a question about the buydown option on my quote.");
    expect(screen.getByText(/\/2000$/)).toBeInTheDocument();
  });

  it("shows a linked, visible error for a too-short message and does not submit", async () => {
    const user = userEvent.setup();
    renderForm();

    const textarea = await screen.findByLabelText("Message");
    await user.type(textarea, "too short");
    await user.click(screen.getByRole("button", { name: /send message/i }));

    const error = await screen.findByText(/message must be 10-2000 characters/i);
    expect(textarea).toHaveAttribute("aria-describedby", expect.stringContaining(error.id));
    expect(textarea).toHaveAttribute("aria-invalid", "true");
    expect(postMock).not.toHaveBeenCalled();
  });

  it("requires a phone when preferred contact is phone, with a linked error", async () => {
    const user = userEvent.setup();
    renderForm({ ...BORROWER_ME, phone: null });

    await fillValidMessage(user);
    await user.click(screen.getByRole("radio", { name: /phone/i }));
    await user.click(screen.getByRole("button", { name: /send message/i }));

    const error = await screen.findByText(/phone is required/i);
    const phoneInput = screen.getByRole("textbox", { name: "Phone" });
    expect(phoneInput).toHaveAttribute("aria-describedby", error.id);
    expect(phoneInput).toHaveAttribute("aria-invalid", "true");
    expect(postMock).not.toHaveBeenCalled();
  });

  it("submits and shows the confirmation state with the reference and LO contact", async () => {
    const user = userEvent.setup();
    postMock.mockResolvedValueOnce({
      data: {
        reference: "SUP-7F3K2",
        lo: {
          name: "Jordan Blake",
          email: "jordan.blake@clearquote-demo.test",
          phone: "8135550199",
        },
      },
      error: undefined,
    });
    renderForm();

    await fillValidMessage(user);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    const status = await screen.findByRole("status");
    expect(status.textContent).toMatch(
      /thanks — we.ll be in touch by email\. your reference is\s*sup-7f3k2\./i,
    );
    expect(status.textContent).toContain("Jordan Blake");
    expect(status.textContent).toContain("jordan.blake@clearquote-demo.test");
    expect(status.textContent).toContain("8135550199");
  });

  it("shows 'Please try again later' on a 429", async () => {
    const user = userEvent.setup();
    postMock.mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "RATE_LIMITED", message: "Please try again later", details: {} } },
    });
    renderForm();

    await fillValidMessage(user);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Please try again later");
  });

  it("is fully keyboard-operable: tab reaches every field and Enter-free Space toggles the radio", async () => {
    const user = userEvent.setup();
    renderForm();

    await screen.findByLabelText("Message");
    await user.tab(); // topic select
    expect(screen.getByLabelText(/what's this about/i)).toHaveFocus();
    await user.tab(); // message
    expect(screen.getByLabelText("Message")).toHaveFocus();
    await user.tab(); // email radio
    expect(screen.getByRole("radio", { name: /email/i })).toHaveFocus();
    await user.keyboard(" ");
    expect(screen.getByRole("radio", { name: /email/i })).toBeChecked();
    // Native radio-group semantics: Tab leaves the group at its checked
    // member (arrow keys move within it), landing next on the phone field.
    await user.tab();
    expect(screen.getByRole("textbox", { name: /phone/i })).toHaveFocus();
    await user.tab(); // submit
    expect(screen.getByRole("button", { name: /send message/i })).toHaveFocus();
  });
});
