import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Tiles } from "./Tiles";

const TILES = {
  clients: 12,
  applications: 34,
  pre_approvals_sent: 5,
  with_property: 6,
  awaiting_review: 7,
  needs_attention: 2,
  stale_quotes: 1,
};

describe("Tiles", () => {
  it("renders all seven tiles as links with the spec.md query parameters", () => {
    render(<Tiles tiles={TILES} loId={null} />);

    expect(screen.getByRole("link", { name: /34.*Applications/ })).toHaveAttribute(
      "href",
      "/applications",
    );
    expect(screen.getByRole("link", { name: /12.*Clients/ })).toHaveAttribute("href", "/clients");
    expect(screen.getByRole("link", { name: /5.*Pre-approvals sent/ })).toHaveAttribute(
      "href",
      "/applications?status=sent_or_later",
    );
    expect(screen.getByRole("link", { name: /6.*With a property/ })).toHaveAttribute(
      "href",
      "/applications?has_property=true",
    );
    expect(screen.getByRole("link", { name: /7.*Awaiting your review/ })).toHaveAttribute(
      "href",
      "/applications?status=Priced,Inquiry,OptionSelected",
    );
    expect(screen.getByRole("link", { name: /2.*Needs attention/ })).toHaveAttribute(
      "href",
      "/applications?status=NeedsAttention",
    );
    expect(screen.getByRole("link", { name: /1.*Stale quotes/ })).toHaveAttribute(
      "href",
      "/applications?status=Stale",
    );
  });

  it("carries the selected lo_id through every tile href", () => {
    render(<Tiles tiles={TILES} loId="lo-42" />);

    expect(screen.getByRole("link", { name: /Applications/ })).toHaveAttribute(
      "href",
      "/applications?lo_id=lo-42",
    );
    expect(screen.getByRole("link", { name: /Pre-approvals sent/ })).toHaveAttribute(
      "href",
      "/applications?status=sent_or_later&lo_id=lo-42",
    );
  });
});
