import { describe, expect, it } from "vitest";

import * as ui from "./index";

describe("@cq/ui barrel exports", () => {
  it("exports every pinned component and type helper", () => {
    expect(typeof ui.Button).toBe("function");
    expect(typeof ui.Card).toBe("function");
    expect(typeof ui.MoneyInput).toBe("function");
    expect(typeof ui.Overlay).toBe("function");
    expect(typeof ui.PercentInput).toBe("function");
    expect(typeof ui.SourceBadge).toBe("function");
    expect(typeof ui.StatusPill).toBe("function");
    expect(typeof ui.Table).toBe("function");
    expect(typeof ui.Tabs).toBe("function");
    expect(typeof ui.Pagination).toBe("function");
    expect(typeof ui.Select).toBe("function");
    expect(typeof ui.MultiSelect).toBe("function");
    expect(typeof ui.Drawer).toBe("function");
    expect(typeof ui.EmptyState).toBe("function");
    expect(typeof ui.ToastProvider).toBe("function");
    expect(typeof ui.useToast).toBe("function");
    expect(typeof ui.useFocusTrap).toBe("function");
    expect(ui.APPLICATION_STATUSES).toHaveLength(12);
    expect(ui.SOURCE_BADGE_SOURCES).toHaveLength(12);
    expect(typeof ui.AuthCard).toBe("function");
    expect(typeof ui.CredentialsForm).toBe("function");
    expect(typeof ui.OtpForm).toBe("function");
    expect(typeof ui.TextField).toBe("function");
    expect(typeof ui.extractErrorMessage).toBe("function");
    expect(typeof ui.useAsyncSubmit).toBe("function");
    expect(typeof ui.isPublicPath).toBe("function");
    expect(ui.STATIC_ASSET_PATTERN).toBeInstanceOf(RegExp);
  });
});
