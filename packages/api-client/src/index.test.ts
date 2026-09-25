import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "./index";

describe("createApiClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("calls GET /health against the given base URL and returns the typed body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "ok",
          checks: { database: "ok", valkey: "ok", minio: "ok", temporal: "ok" },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const api = createApiClient("http://localhost:8000");
    const { data, error } = await api.GET("/health");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledRequest = fetchMock.mock.calls[0][0] as Request;
    expect(calledRequest.url).toBe("http://localhost:8000/health");
    expect(error).toBeUndefined();
    expect(data?.status).toBe("ok");
    expect(data?.checks.database).toBe("ok");
  });
});
