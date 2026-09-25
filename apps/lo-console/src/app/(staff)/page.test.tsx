import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DashboardPage from "./page";
import ClientsPage from "./clients/page";
import ApplicationsPage from "./applications/page";
import OutboxPage from "./outbox/page";
import IntegrationsPage from "./admin/integrations/page";
import SettingsPage from "./admin/settings/page";

// P5/P6 foundation: each reserved route renders its heading and the item
// that builds it. (The session behaviour the old placeholder home tested --
// /me, 401 -> logout -> /login, Sign out -- moved to
// src/features/shell/StaffSessionProvider.test.tsx and StaffShell.test.tsx.)
describe("(staff) stub pages", () => {
  it.each([
    ["Dashboard", DashboardPage, "CQ-025"],
    ["Clients", ClientsPage, "CQ-026"],
    ["Applications", ApplicationsPage, "CQ-027"],
    ["Outbox", OutboxPage, "CQ-029"],
    ["Integrations", IntegrationsPage, "CQ-029"],
    ["Settings", SettingsPage, "CQ-029"],
  ])("%s says which item builds it", (title, Page, item) => {
    render(<Page />);
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
    expect(screen.getByText(`Built in ${item}`)).toBeInTheDocument();
  });
});
