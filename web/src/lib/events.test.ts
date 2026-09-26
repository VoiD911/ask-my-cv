import { describe, expect, it } from "vitest";
import { isAskEvent } from "./events";

describe("isAskEvent", () => {
  it("accepts a stage.start event", () => {
    expect(isAskEvent({ type: "stage.start", name: "reception", ts: 1.5 })).toBe(true);
  });

  it("accepts a stage.end event with attrs", () => {
    expect(
      isAskEvent({
        type: "stage.end",
        name: "quota",
        status: "blocked",
        duration_ms: 3.2,
        attrs: { reason: "rate_limited" },
      }),
    ).toBe(true);
  });

  it("rejects a stage.end event with an unknown status", () => {
    expect(
      isAskEvent({
        type: "stage.end",
        name: "quota",
        status: "weird",
        duration_ms: 3.2,
        attrs: {},
      }),
    ).toBe(false);
  });

  it("accepts an llm.progress event", () => {
    expect(isAskEvent({ type: "llm.progress", tokens: 12 })).toBe(true);
  });

  it("accepts an answer event", () => {
    expect(isAskEvent({ type: "answer", text: "réponse" })).toBe(true);
  });

  it("accepts a done event with null answer_override and trace_id", () => {
    expect(
      isAskEvent({
        type: "done",
        tokens_in: 10,
        tokens_out: 20,
        cost_usd: 0.002,
        latency_ms: 512,
        sources: ["cv.md"],
        answer_override: null,
        trace_id: null,
      }),
    ).toBe(true);
  });

  it("accepts a done event with string answer_override and trace_id", () => {
    expect(
      isAskEvent({
        type: "done",
        tokens_in: 10,
        tokens_out: 20,
        cost_usd: 0.002,
        latency_ms: 512,
        sources: [],
        answer_override: "réponse de repli",
        trace_id: "abc-123",
      }),
    ).toBe(true);
  });

  it("rejects a done event missing a required field", () => {
    expect(
      isAskEvent({
        type: "done",
        tokens_in: 10,
        tokens_out: 20,
        cost_usd: 0.002,
        sources: [],
        answer_override: null,
        trace_id: null,
      }),
    ).toBe(false);
  });

  it("rejects an unknown event type", () => {
    expect(isAskEvent({ type: "stage.unknown" })).toBe(false);
  });

  it("rejects non-object values", () => {
    expect(isAskEvent(null)).toBe(false);
    expect(isAskEvent("stage.start")).toBe(false);
    expect(isAskEvent(42)).toBe(false);
  });
});
