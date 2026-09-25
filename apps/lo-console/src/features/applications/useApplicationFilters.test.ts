import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));
let currentSearch = "";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => "/applications",
  useSearchParams: () => new URLSearchParams(currentSearch),
}));

import { useApplicationFilters } from "./useApplicationFilters";

describe("useApplicationFilters", () => {
  it("parses the current URL into filters", () => {
    currentSearch = "status=needs_attention&page=2";
    const { result } = renderHook(() => useApplicationFilters());
    expect(result.current.filters.status).toEqual(["needs_attention"]);
    expect(result.current.filters.page).toBe(2);
  });

  it("pushes a new URL on setFilters and resets page to 1", () => {
    currentSearch = "page=3";
    const { result } = renderHook(() => useApplicationFilters());
    act(() => result.current.setFilters({ q: "grace" }));
    expect(pushMock).toHaveBeenCalledWith("/applications?q=grace");
  });

  it("keeps the given page when only page changes", () => {
    currentSearch = "";
    const { result } = renderHook(() => useApplicationFilters());
    act(() => result.current.setFilters({ page: 2 }));
    expect(pushMock).toHaveBeenCalledWith("/applications?page=2");
  });

  it("clearFilters pushes the bare pathname", () => {
    currentSearch = "status=priced&page=2";
    const { result } = renderHook(() => useApplicationFilters());
    act(() => result.current.clearFilters());
    expect(pushMock).toHaveBeenCalledWith("/applications");
  });
});
