import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

import { ApplicationCard } from "./ApplicationCard";
import type { PortalApplicationOut } from "./api";

const BASE: PortalApplicationOut = {
  id: "a1",
  stage: "in_review",
  label: "Your loan officer is reviewing your numbers",
  next_action: { type: "none" },
  secondary_report_token: null,
  lo: { name: "Taylor Morgan", phone: "8135551234", email: "taylor.morgan@clearquote-demo.test" },
};

describe("ApplicationCard", () => {
  afterEach(() => {
    pushMock.mockReset();
  });

  it("renders the label, progress bar and LO contact card", () => {
    render(<ApplicationCard application={BASE} />);
    expect(screen.getByText("Your loan officer is reviewing your numbers")).toBeInTheDocument();
    expect(screen.getByText("Applied")).toBeInTheDocument();
    expect(screen.getByText("Taylor Morgan")).toBeInTheDocument();
    expect(screen.getByText("taylor.morgan@clearquote-demo.test")).toBeInTheDocument();
    expect(screen.getByText("8135551234")).toBeInTheDocument();
  });

  it("navigates to the report on 'See your numbers' (view_report)", async () => {
    render(
      <ApplicationCard
        application={{
          ...BASE,
          stage: "preapproved",
          next_action: { type: "view_report", report_token: "tok-1" },
        }}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "See your numbers" }));
    expect(pushMock).toHaveBeenCalledWith("/report/tok-1");
  });

  it("navigates to /apply on 'Continue your application' (draft)", async () => {
    render(
      <ApplicationCard
        application={{
          ...BASE,
          id: "draft-1",
          stage: "draft",
          label: "Continue your application",
          next_action: { type: "continue_application", draft_id: "draft-1" },
          lo: null,
        }}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Continue your application" }));
    expect(pushMock).toHaveBeenCalledWith("/apply");
    expect(screen.queryByText("Applied")).not.toBeInTheDocument(); // no progress bar for draft
  });

  it("renders no primary button and no progress bar for closed, and no LO card when null", () => {
    render(
      <ApplicationCard
        application={{
          ...BASE,
          stage: "closed",
          label: "This application is closed",
          next_action: { type: "none" },
          lo: null,
        }}
      />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText("Applied")).not.toBeInTheDocument();
    expect(screen.queryByText("Taylor Morgan")).not.toBeInTheDocument();
  });

  it("shows a secondary 'View your numbers' link alongside next_action = none", () => {
    render(
      <ApplicationCard
        application={{
          ...BASE,
          stage: "option_selected",
          label: "You chose an option — Taylor will be in touch",
          next_action: { type: "none" },
          secondary_report_token: "tok-2",
        }}
      />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View your numbers" })).toHaveAttribute(
      "href",
      "/report/tok-2",
    );
  });
});
