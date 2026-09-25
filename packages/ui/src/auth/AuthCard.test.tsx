import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthCard } from "./AuthCard";

describe("AuthCard", () => {
  it("renders the heading and children, with no subtitle by default", () => {
    render(
      <AuthCard heading="Clear Quote — LO Console">
        <p>form goes here</p>
      </AuthCard>,
    );

    expect(screen.getByRole("heading", { name: "Clear Quote — LO Console" })).toBeInTheDocument();
    expect(screen.getByText("form goes here")).toBeInTheDocument();
    expect(screen.queryByText(/sign in to see your numbers/i)).not.toBeInTheDocument();
  });

  it("renders a subtitle when provided", () => {
    render(
      <AuthCard heading="Clear Quote" subtitle="Sign in to see your numbers">
        <p>form goes here</p>
      </AuthCard>,
    );

    expect(screen.getByRole("heading", { name: "Clear Quote" })).toBeInTheDocument();
    expect(screen.getByText("Sign in to see your numbers")).toBeInTheDocument();
  });
});
