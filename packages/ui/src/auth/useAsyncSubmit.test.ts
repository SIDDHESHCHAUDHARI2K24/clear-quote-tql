import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useAsyncSubmit } from "./useAsyncSubmit";

const FALLBACK = "Something went wrong. Try again.";

describe("useAsyncSubmit", () => {
  it("sets pending while the submit promise is in flight and clears it after", async () => {
    let resolveSubmit: (value: { ok: true; data: string }) => void = () => {};
    const submit = vi.fn(
      () =>
        new Promise<{ ok: true; data: string }>((resolve) => {
          resolveSubmit = resolve;
        }),
    );
    const { result } = renderHook(() => useAsyncSubmit(submit, { fallbackError: FALLBACK }));

    expect(result.current.pending).toBe(false);

    act(() => {
      void result.current.run("x");
    });

    await waitFor(() => expect(result.current.pending).toBe(true));

    act(() => resolveSubmit({ ok: true, data: "done" }));

    await waitFor(() => expect(result.current.pending).toBe(false));
  });

  it("calls onSuccess with the data and the values on a successful result", async () => {
    const submit = vi.fn().mockResolvedValue({ ok: true, data: { id: 1 } });
    const onSuccess = vi.fn();
    const { result } = renderHook(() =>
      useAsyncSubmit(submit, { fallbackError: FALLBACK, onSuccess }),
    );

    await act(() => result.current.run({ email: "a@b.com" }));

    expect(onSuccess).toHaveBeenCalledWith({ id: 1 }, { email: "a@b.com" });
    expect(result.current.error).toBeNull();
  });

  it("sets a message from a rejected result and does not call onSuccess", async () => {
    const submit = vi.fn().mockResolvedValue({
      ok: false,
      error: { error: { code: "X", message: "Nope" } },
    });
    const onSuccess = vi.fn();
    const { result } = renderHook(() =>
      useAsyncSubmit(submit, { fallbackError: FALLBACK, onSuccess }),
    );

    await act(() => result.current.run({}));

    expect(result.current.error).toBe("Nope");
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("falls back to the fallback message when submit throws", async () => {
    const submit = vi.fn().mockRejectedValue(new Error("network down"));
    const { result } = renderHook(() => useAsyncSubmit(submit, { fallbackError: FALLBACK }));

    await act(() => result.current.run({}));

    expect(result.current.error).toBe(FALLBACK);
    expect(result.current.pending).toBe(false);
  });

  it("clears a previous error at the start of the next run", async () => {
    const submit = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, error: {} })
      .mockResolvedValueOnce({ ok: true, data: null });
    const { result } = renderHook(() => useAsyncSubmit(submit, { fallbackError: FALLBACK }));

    await act(() => result.current.run({}));
    expect(result.current.error).toBe(FALLBACK);

    await act(() => result.current.run({}));
    expect(result.current.error).toBeNull();
  });
});
