import { describe, expect, it } from "vitest";
import { createSseParser, type SseMessage } from "./sse";

function collector(): { messages: SseMessage[]; onEvent: (m: SseMessage) => void } {
  const messages: SseMessage[] = [];
  return { messages, onEvent: (m) => messages.push(m) };
}

describe("createSseParser", () => {
  it("parses a single complete event in one chunk", () => {
    const { messages, onEvent } = collector();
    const parser = createSseParser(onEvent);
    parser.push('event: stage.start\ndata: {"name":"reception"}\n\n');
    expect(messages).toEqual([{ event: "stage.start", data: '{"name":"reception"}' }]);
    expect(parser.errorCount).toBe(0);
  });

  it("parses multiple events packed in one chunk", () => {
    const { messages, onEvent } = collector();
    const parser = createSseParser(onEvent);
    parser.push(
      'event: stage.start\ndata: {"a":1}\n\nevent: stage.end\ndata: {"b":2}\n\n',
    );
    expect(messages).toEqual([
      { event: "stage.start", data: '{"a":1}' },
      { event: "stage.end", data: '{"b":2}' },
    ]);
    expect(parser.errorCount).toBe(0);
  });

  it("reassembles an event split across many arbitrary chunks", () => {
    const { messages, onEvent } = collector();
    const parser = createSseParser(onEvent);
    const full = 'event: llm.progress\ndata: {"tokens":42}\n\n';
    // Split at every character to simulate the worst-case network chunking.
    for (const ch of full) {
      parser.push(ch);
    }
    expect(messages).toEqual([{ event: "llm.progress", data: '{"tokens":42}' }]);
    expect(parser.errorCount).toBe(0);
  });

  it("splits a chunk exactly between the two bytes of a CRLF blank line", () => {
    const { messages, onEvent } = collector();
    const parser = createSseParser(onEvent);
    parser.push('event: done\r\ndata: {"x":1}\r');
    parser.push('\n\r\n');
    expect(messages).toEqual([{ event: "done", data: '{"x":1}' }]);
  });

  it("accepts \\r\\n line endings", () => {
    const { messages, onEvent } = collector();
    const parser = createSseParser(onEvent);
    parser.push('event: answer\r\ndata: {"text":"hi"}\r\n\r\n');
    expect(messages).toEqual([{ event: "answer", data: '{"text":"hi"}' }]);
    expect(parser.errorCount).toBe(0);
  });

  it("accepts \\n line endings", () => {
    const { messages, onEvent } = collector();
    const parser = createSseParser(onEvent);
    parser.push('event: answer\ndata: {"text":"hi"}\n\n');
    expect(messages).toEqual([{ event: "answer", data: '{"text":"hi"}' }]);
  });

  it("defaults the event name to 'message' when no event: field is present", () => {
    const { messages, onEvent } = collector();
    const parser = createSseParser(onEvent);
    parser.push('data: {"x":1}\n\n');
    expect(messages).toEqual([{ event: "message", data: '{"x":1}' }]);
  });

  it("joins multiple data: lines within one block with newlines", () => {
    const { messages, onEvent } = collector();
    const parser = createSseParser(onEvent);
    parser.push("event: answer\ndata: line1\ndata: line2\n\n");
    expect(messages).toEqual([{ event: "answer", data: "line1\nline2" }]);
  });

  it("ignores a block with no data: line and counts an error", () => {
    const { messages, onEvent } = collector();
    const parser = createSseParser(onEvent);
    parser.push("event: stage.start\n\n");
    expect(messages).toEqual([]);
    expect(parser.errorCount).toBe(1);
  });

  it("ignores an unrecognized field line and counts an error, but still emits the rest of the block", () => {
    const { messages, onEvent } = collector();
    const parser = createSseParser(onEvent);
    parser.push('garbled-line-without-known-prefix\ndata: {"ok":true}\n\n');
    expect(messages).toEqual([{ event: "message", data: '{"ok":true}' }]);
    expect(parser.errorCount).toBe(1);
  });

  it("ignores SSE comment lines without counting them as errors", () => {
    const { messages, onEvent } = collector();
    const parser = createSseParser(onEvent);
    parser.push(': keep-alive\ndata: {"ok":true}\n\n');
    expect(messages).toEqual([{ event: "message", data: '{"ok":true}' }]);
    expect(parser.errorCount).toBe(0);
  });

  it("keeps an incomplete trailing block buffered until the terminator arrives", () => {
    const { messages, onEvent } = collector();
    const parser = createSseParser(onEvent);
    parser.push('event: stage.end\ndata: {"partial"');
    expect(messages).toEqual([]);
    parser.push(':true}\n\n');
    expect(messages).toEqual([{ event: "stage.end", data: '{"partial":true}' }]);
  });
});
