import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchModels } from "./models";

describe("fetchModels", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches and validates the /models payload", async () => {
    const payload = { default: "gpt-mini", models: [{ id: "gpt-mini", provider: "openai" }] };
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchModels({ baseUrl: "/api" });

    expect(result).toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith("/api/models", expect.objectContaining({ method: "GET" }));
  });

  it("throws when the response is not ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("boom", { status: 500 })),
    );

    await expect(fetchModels()).rejects.toThrow(/500/);
  });

  it("throws when the payload does not match the expected shape", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ nope: true }), { status: 200 })),
    );

    await expect(fetchModels()).rejects.toThrow(/mal formée/);
  });

  it("propagates AbortError untouched", async () => {
    const abortError = new DOMException("aborted", "AbortError");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw abortError;
      }),
    );

    await expect(fetchModels()).rejects.toBe(abortError);
  });
});
