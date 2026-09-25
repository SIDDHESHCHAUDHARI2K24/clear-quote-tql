import { useState } from "react";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { uploadMock, deleteMock } = vi.hoisted(() => ({
  uploadMock: vi.fn(),
  deleteMock: vi.fn(),
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return { ...actual, uploadDocument: uploadMock, deleteDocument: deleteMock };
});

import { setPath } from "../paths";
import type { JsonRecord } from "../paths";
import { IncomeTab } from "./IncomeTab";

function Harness({
  initial = {},
  errors = {},
  occupancy = "str",
}: {
  initial?: JsonRecord;
  errors?: Record<string, string>;
  occupancy?: string;
}) {
  const [data, setData] = useState<JsonRecord>(initial);
  return (
    <IncomeTab
      data={data}
      set={(path, value) => setData((prev) => setPath(prev, path, value))}
      errorFor={(path) => errors[path]}
      disabled={false}
      draftId="d1111111-1111-1111-1111-111111111111"
      occupancy={occupancy}
    />
  );
}

function makeFile(name: string, sizeBytes: number, type = "application/pdf"): File {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: sizeBytes });
  return file;
}

describe("IncomeTab (CQ-032 spec.md tab 3)", () => {
  afterEach(() => {
    uploadMock.mockReset();
    deleteMock.mockReset();
  });

  it("hints income is required for a primary residence", () => {
    render(<Harness occupancy="primary" />);
    expect(
      screen.getByText(/Required since this will be the home you live in/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Employer")).toBeInTheDocument();
  });

  it("marks income fields optional for an investment property", () => {
    render(<Harness occupancy="str" />);
    expect(screen.getByLabelText("Employer (optional)")).toBeInTheDocument();
  });

  it("rejects an over-limit file client-side without calling the API (AC7)", async () => {
    render(<Harness />);
    const input = screen.getByLabelText("File");
    fireEvent.change(input, { target: { files: [makeFile("stub.pdf", 11 * 1024 * 1024)] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    await waitFor(() =>
      expect(screen.getByText("Files must be 10 MB or smaller.")).toBeInTheDocument(),
    );
    expect(uploadMock).not.toHaveBeenCalled();
  });

  it("rejects an unsupported file type client-side without calling the API (AC7)", async () => {
    render(<Harness />);
    const input = screen.getByLabelText("File");
    fireEvent.change(input, {
      target: { files: [makeFile("virus.exe", 1000, "application/octet-stream")] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    await waitFor(() =>
      expect(screen.getByText("Only PDF, JPG and PNG files are accepted.")).toBeInTheDocument(),
    );
    expect(uploadMock).not.toHaveBeenCalled();
  });

  it("uploads a valid file and lists it", async () => {
    uploadMock.mockResolvedValueOnce({
      data: {
        id: "doc-1",
        doc_type: "pay_stub",
        filename: "stub.pdf",
        content_type: "application/pdf",
        size_bytes: 1000,
        uploaded_at: "2026-01-01T00:00:00Z",
      },
      error: undefined,
    });
    render(<Harness />);
    fireEvent.change(screen.getByLabelText("File"), {
      target: { files: [makeFile("stub.pdf", 1000)] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    await waitFor(() => expect(screen.getByText(/Pay stub: stub.pdf/)).toBeInTheDocument());
    expect(uploadMock).toHaveBeenCalledTimes(1);
  });

  it("removes an uploaded document", async () => {
    deleteMock.mockResolvedValueOnce({ response: { ok: true } });
    render(
      <Harness
        initial={{
          documents: [
            {
              id: "doc-1",
              doc_type: "w2",
              filename: "w2.pdf",
              content_type: "application/pdf",
              size_bytes: 1000,
              uploaded_at: "2026-01-01T00:00:00Z",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText(/W-2: w2.pdf/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

    await waitFor(() => expect(screen.queryByText(/W-2: w2.pdf/)).not.toBeInTheDocument());
    expect(deleteMock).toHaveBeenCalledWith("d1111111-1111-1111-1111-111111111111", "doc-1");
  });
});
