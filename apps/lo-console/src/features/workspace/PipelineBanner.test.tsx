import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, PATCH: vi.fn() }),
}));

import { PipelineBanner } from "./PipelineBanner";
import { makeSummary } from "./test-fixtures";
import { WorkspaceProvider } from "./WorkspaceProvider";

const APPLICATION_ID = "11111111-1111-1111-1111-111111111111";

// spec.md AC7: the banner shows the running stage name while the pipeline
// is active and disappears once it reaches a terminal stage.
describe("PipelineBanner (AC7)", () => {
  afterEach(() => {
    getMock.mockReset();
  });

  it("shows the stage name while the pipeline is running", async () => {
    getMock.mockResolvedValueOnce({
      data: makeSummary({ last_pipeline_stage: "enriching" }),
      response: { status: 200 },
    });

    render(
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <PipelineBanner />
      </WorkspaceProvider>,
    );

    expect(await screen.findByRole("status")).toHaveTextContent("Pipeline running: Enriching");
  });

  it("renders nothing once the stage is terminal", async () => {
    getMock.mockResolvedValueOnce({
      data: makeSummary({ last_pipeline_stage: "priced" }),
      response: { status: 200 },
    });

    render(
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <PipelineBanner />
      </WorkspaceProvider>,
    );

    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders nothing when the pipeline has never run", async () => {
    getMock.mockResolvedValueOnce({
      data: makeSummary({ last_pipeline_stage: null }),
      response: { status: 200 },
    });

    render(
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <PipelineBanner />
      </WorkspaceProvider>,
    );

    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
