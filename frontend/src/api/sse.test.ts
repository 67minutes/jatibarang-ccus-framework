import { describe, expect, it } from "vitest";
import { SseFrameParser, type ParsedFrame } from "./sse";
import { readFixture } from "../test/fixture";

const rawStream = readFixture("src/test/fixtures/stream.sse");

function parseAll(chunks: string[]): ParsedFrame[] {
  const parser = new SseFrameParser();
  const frames: ParsedFrame[] = [];
  for (const chunk of chunks) frames.push(...parser.push(chunk));
  return frames;
}

describe("SseFrameParser", () => {
  it("parses every frame from a real captured stream", () => {
    const frames = parseAll([rawStream]);
    const events = frames.map((f) => f.event);
    expect(events[0]).toBe("run_started");
    expect(events).toContain("result");
    expect(frames.filter((f) => f.event === "warning").length).toBeGreaterThan(0);
    // Each frame carries valid JSON data with a matching event field.
    for (const frame of frames) {
      const data = JSON.parse(frame.data);
      expect(data.event).toBe(frame.event);
    }
  });

  it("is invariant to chunk boundaries (byte-by-byte)", () => {
    const whole = parseAll([rawStream]);
    const byChar = parseAll([...rawStream]); // one character per push
    expect(byChar.map((f) => f.event)).toEqual(whole.map((f) => f.event));
  });

  it("is invariant to arbitrary split points", () => {
    const whole = parseAll([rawStream]);
    const mid = Math.floor(rawStream.length / 2);
    const split = parseAll([rawStream.slice(0, mid), rawStream.slice(mid)]);
    expect(split.map((f) => f.event)).toEqual(whole.map((f) => f.event));
  });

  it("carries a full ScreenResult in the terminal result frame", () => {
    const frames = parseAll([rawStream]);
    const result = frames.find((f) => f.event === "result");
    expect(result).toBeDefined();
    const payload = JSON.parse(result!.data);
    expect(payload.payload.result.request_fingerprint).toBeTruthy();
    expect(Array.isArray(payload.payload.result.plans)).toBe(true);
  });

  it("handles CRLF frame separators", () => {
    const crlf =
      "id: 0\r\nevent: warning\r\ndata: {\"event\":\"warning\",\"message\":\"x\"}\r\n\r\n";
    const frames = parseAll([crlf]);
    expect(frames).toHaveLength(1);
    expect(frames[0].event).toBe("warning");
  });

  it("ignores comment-only heartbeat frames", () => {
    const frames = parseAll([": keep-alive\n\n"]);
    expect(frames).toHaveLength(0);
  });
});
