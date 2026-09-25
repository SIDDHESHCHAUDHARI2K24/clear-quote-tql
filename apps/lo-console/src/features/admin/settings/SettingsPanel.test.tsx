import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock }),
}));

import { SettingsPanel } from "./SettingsPanel";

describe("SettingsPanel (AC6)", () => {
  afterEach(() => {
    getMock.mockReset();
  });

  it("lists every setting with its value and source", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        settings: [
          {
            key: "fee_lender_processing",
            value: 995.0,
            description: "Lender processing fee",
            source: "settings_table",
          },
          {
            key: "default_down_payment_primary_pct",
            value: 0.2,
            description: "Default primary down payment",
            source: "code_default",
          },
        ],
      },
      response: { status: 200 },
    });

    render(<SettingsPanel />);

    expect(await screen.findByText("fee_lender_processing")).toBeInTheDocument();
    expect(screen.getByText("995")).toBeInTheDocument();
    expect(screen.getByText("Seed")).toBeInTheDocument();
    expect(screen.getByText("default_down_payment_primary_pct")).toBeInTheDocument();
    expect(screen.getByText("Config default")).toBeInTheDocument();
  });
});
