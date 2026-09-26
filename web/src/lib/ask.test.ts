import { afterEach, describe, expect, it, vi } from "vitest";
import { ask, AskError } from "./ask";
import type { AskEvent } from "./events";

function toHex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Découpe `text` (encodé en UTF-8) en morceaux de taille pseudo-aléatoire. */
function chunkedStream(text: string, seed = 1): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text);
  let offset = 0;
  let state = seed;
  const nextSize = () => {
    // PRNG minimal mais déterministe : évite un flake tout en variant la découpe.
    state = (state * 1103515245 + 12345) & 0x7fffffff;
    return 1 + (state % 5);
  };
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (offset >= bytes.length) {
        controller.close();
        return;
      }
      const size = nextSize();
      const slice = bytes.slice(offset, offset + size);
      offset += slice.length;
      controller.enqueue(slice);
    },
  });
}

function sseBody(events: Array<{ event: string; data: unknown }>): string {
  return events.map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`).join("");
}

describe("ask", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the SHA-256 of the exact bytes it transmits in x-amz-content-sha256", async () => {
    let capturedInit: RequestInit | undefined;
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      capturedInit = init;
      return new Response(chunkedStream(sseBody([{ event: "done", data: { tokens_in: 1 } }])), {
        status: 200,
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const events: AskEvent[] = [];
    await ask({ question: "Quelle est ton expérience ?", onEvent: (e) => events.push(e) });

    expect(capturedInit).toBeDefined();
    const sentBytes = capturedInit!.body as Uint8Array<ArrayBuffer>;
    const expectedDigest = await crypto.subtle.digest("SHA-256", sentBytes);
    const expectedHex = toHex(expectedDigest);

    const headers = new Headers(capturedInit!.headers);
    expect(headers.get("x-amz-content-sha256")).toBe(expectedHex);
    expect(headers.get("content-type")).toBe("application/json");

    const sentText = new TextDecoder().decode(sentBytes);
    expect(JSON.parse(sentText)).toEqual({ question: "Quelle est ton expérience ?" });
  });

  it("includes model in the body only when provided", async () => {
    let capturedInit: RequestInit | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        capturedInit = init;
        return new Response(chunkedStream(""), { status: 200 });
      }),
    );

    await ask({ question: "q", model: "gpt-mini", onEvent: () => {} });
    const sentText = new TextDecoder().decode(capturedInit!.body as Uint8Array);
    expect(JSON.parse(sentText)).toEqual({ question: "q", model: "gpt-mini" });
  });

  it("parses a realistic stream split into arbitrary chunks into typed events", async () => {
    const body = sseBody([
      { event: "stage.start", data: { type: "stage.start", name: "reception", ts: 0.1 } },
      {
        event: "stage.end",
        data: { type: "stage.end", name: "reception", status: "ok", duration_ms: 1.2, attrs: {} },
      },
      { event: "llm.progress", data: { type: "llm.progress", tokens: 5 } },
      { event: "answer", data: { type: "answer", text: "Bonjour" } },
      {
        event: "done",
        data: {
          type: "done",
          tokens_in: 10,
          tokens_out: 5,
          cost_usd: 0.001,
          latency_ms: 42,
          sources: ["cv.md"],
          answer_override: null,
          trace_id: "t-1",
        },
      },
    ]);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(chunkedStream(body, 7), { status: 200 })),
    );

    const events: AskEvent[] = [];
    await ask({ question: "q", onEvent: (e) => events.push(e) });

    expect(events.map((e) => e.type)).toEqual([
      "stage.start",
      "stage.end",
      "llm.progress",
      "answer",
      "done",
    ]);
    const done = events[4];
    expect(done).toMatchObject({ type: "done", trace_id: "t-1", sources: ["cv.md"] });
  });

  it("throws a typed invalid_question AskError on 422", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: [] }), { status: 422 })),
    );

    const error = await ask({ question: "q", onEvent: () => {} }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(AskError);
    expect((error as AskError).kind).toBe("invalid_question");
    expect((error as AskError).status).toBe(422);
  });

  it("throws a typed signature AskError on 403", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("forbidden", { status: 403 })),
    );

    const error = await ask({ question: "q", onEvent: () => {} }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(AskError);
    expect((error as AskError).kind).toBe("signature");
  });

  it("throws a typed unavailable AskError on other error statuses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("oops", { status: 500 })),
    );

    const error = await ask({ question: "q", onEvent: () => {} }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(AskError);
    expect((error as AskError).kind).toBe("unavailable");
    expect((error as AskError).status).toBe(500);
  });

  it("throws unavailable when fetch itself rejects (network failure)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("network down");
      }),
    );

    const error = await ask({ question: "q", onEvent: () => {} }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(AskError);
    expect((error as AskError).kind).toBe("unavailable");
  });

  it("propagates AbortError when the signal is aborted before the request starts", async () => {
    const controller = new AbortController();
    controller.abort();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        if (init?.signal?.aborted) {
          const err = new DOMException("aborted", "AbortError");
          throw err;
        }
        return new Response(chunkedStream(""), { status: 200 });
      }),
    );

    await expect(
      ask({ question: "q", signal: controller.signal, onEvent: () => {} }),
    ).rejects.toMatchObject({ name: "AbortError" });
  });

  it("ignores unparseable SSE data payloads instead of throwing", async () => {
    const body = 'event: answer\ndata: not-json\n\nevent: answer\ndata: {"type":"answer","text":"ok"}\n\n';
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(chunkedStream(body, 3), { status: 200 })),
    );

    const events: AskEvent[] = [];
    await ask({ question: "q", onEvent: (e) => events.push(e) });
    expect(events).toEqual([{ type: "answer", text: "ok" }]);
  });
});
