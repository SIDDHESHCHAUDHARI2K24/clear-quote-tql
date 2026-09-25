import { useState } from "react";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { setPath } from "../paths";
import type { JsonRecord } from "../paths";
import { ConsentTab } from "./ConsentTab";

function Harness({
  initial = {},
  errors = {},
}: {
  initial?: JsonRecord;
  errors?: Record<string, string>;
}) {
  const [data, setData] = useState<JsonRecord>(initial);
  return (
    <ConsentTab
      data={data}
      set={(path, value) => setData((prev) => setPath(prev, path, value))}
      errorFor={(path) => errors[path]}
      disabled={false}
      expectedName="Tina Tampa"
      consentVersion="apply-v1"
      consentText="By continuing you agree to a soft credit pull."
    />
  );
}

describe("ConsentTab (CQ-032 spec.md tab 4)", () => {
  it("shows the consent text and version that will be hashed", () => {
    render(<Harness />);
    expect(screen.getByText("By continuing you agree to a soft credit pull.")).toBeInTheDocument();
    expect(screen.getByText("Version apply-v1")).toBeInTheDocument();
  });

  it("checking a box updates the corresponding path", () => {
    let latest: JsonRecord = {};
    function Wrapper() {
      const [data, setData] = useState<JsonRecord>({});
      latest = data;
      return (
        <ConsentTab
          data={data}
          set={(path, value) => setData((prev) => setPath(prev, path, value))}
          errorFor={() => undefined}
          disabled={false}
          expectedName="Tina Tampa"
          consentVersion="apply-v1"
          consentText="text"
        />
      );
    }
    render(<Wrapper />);
    fireEvent.click(screen.getByLabelText(/soft credit pull/));
    expect(latest.soft_pull_authorized).toBe(true);
  });

  it("hints at the expected name and surfaces a mismatch error", () => {
    render(
      <Harness errors={{ typed_name: "Type your full name exactly as entered on step 1." }} />,
    );
    expect(screen.getByLabelText("Type your full name to sign")).toHaveAttribute(
      "placeholder",
      "Tina Tampa",
    );
    expect(
      screen.getByText("Type your full name exactly as entered on step 1."),
    ).toBeInTheDocument();
  });
});
