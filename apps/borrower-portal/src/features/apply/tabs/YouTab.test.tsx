import { useState } from "react";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { setPath } from "../paths";
import type { JsonRecord } from "../paths";
import { YouTab } from "./YouTab";

function Harness({
  initial = {},
  errors = {},
}: {
  initial?: JsonRecord;
  errors?: Record<string, string>;
}) {
  const [data, setData] = useState<JsonRecord>(initial);
  return (
    <YouTab
      data={data}
      set={(path, value) => setData((prev) => setPath(prev, path, value))}
      errorFor={(path) => errors[path]}
      disabled={false}
      email="tina@example.com"
    />
  );
}

describe("YouTab (CQ-032 spec.md tab 1)", () => {
  it("shows the account email read-only", () => {
    render(<Harness />);
    expect(screen.getByLabelText("Email")).toHaveValue("tina@example.com");
    expect(screen.getByLabelText("Email")).toBeDisabled();
  });

  it("reveals a prior-address section once residence is under 24 months", () => {
    render(<Harness />);
    expect(screen.queryByText("Prior address")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Years there"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Months there"), { target: { value: "2" } });

    expect(screen.getByRole("heading", { name: "Prior address" })).toBeInTheDocument();
  });

  it("keeps the prior-address section hidden at 24+ months", () => {
    render(<Harness />);
    fireEvent.change(screen.getByLabelText("Years there"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Months there"), { target: { value: "0" } });
    expect(screen.queryByText("Prior address")).not.toBeInTheDocument();
  });

  it("shows co-borrower fields only once 'Add a co-borrower' is checked", () => {
    render(<Harness />);
    expect(screen.queryByRole("heading", { name: "Co-borrower" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Add a co-borrower"));
    expect(screen.getByRole("heading", { name: "Co-borrower" })).toBeInTheDocument();
  });

  it("shows a 'saved' hint for the SSN instead of the digits once ssn_set is true", () => {
    render(<Harness initial={{ ssn_set: true, ssn_last4: "6789" }} />);
    expect(screen.getByLabelText("Social Security number")).toHaveValue("");
    expect(screen.getByText(/SSN on file: •••-••-6789/)).toBeInTheDocument();
  });

  it("links a field's error via aria-describedby (AC8)", () => {
    render(<Harness errors={{ first_name: "This field is required." }} />);
    const input = screen.getByLabelText("First name");
    const describedBy = input.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)).toHaveTextContent("This field is required.");
  });
});
