import type { ProgressEvent, ScreenRequest, ScreenResult } from "./types";
import { ApiError } from "./client";

/**
 * SSE client for `POST /screen/stream`. `EventSource` can't POST, so we use
 * fetch + a ReadableStream reader and parse SSE frames by hand. The frame
 * parser is exported and unit-tested against recorded backend streams.
 */

export interface ParsedFrame {
  id?: string;
  event?: string;
  data: string;
}

/**
 * Incremental SSE frame parser. Feed it chunks; it yields complete frames.
 * Frames are separated by a blank line; `data:` lines accumulate.
 */
export class SseFrameParser {
  private buffer = "";

  push(chunk: string): ParsedFrame[] {
    this.buffer += chunk;
    const frames: ParsedFrame[] = [];
    let sep: number;
    // Frames end at a blank line (\n\n), tolerating \r\n.
    while ((sep = this.indexOfBoundary(this.buffer)) !== -1) {
      const rawEnd = sep.valueOf();
      const raw = this.buffer.slice(0, rawEnd);
      this.buffer = this.buffer.slice(this.skipBoundary(this.buffer, rawEnd));
      const frame = parseFrame(raw);
      if (frame) frames.push(frame);
    }
    return frames;
  }

  private indexOfBoundary(s: string): number {
    const lf = s.indexOf("\n\n");
    const crlf = s.indexOf("\r\n\r\n");
    if (lf === -1) return crlf;
    if (crlf === -1) return lf;
    return Math.min(lf, crlf);
  }

  private skipBoundary(s: string, at: number): number {
    return s.startsWith("\r\n\r\n", at) ? at + 4 : at + 2;
  }
}

function parseFrame(raw: string): ParsedFrame | null {
  const lines = raw.split(/\r?\n/);
  let id: string | undefined;
  let event: string | undefined;
  const dataParts: string[] = [];
  for (const line of lines) {
    if (line === "" || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "id") id = value;
    else if (field === "event") event = value;
    else if (field === "data") dataParts.push(value);
  }
  if (dataParts.length === 0 && event === undefined) return null;
  return { id, event, data: dataParts.join("\n") };
}

export interface StreamHandlers {
  onEvent: (event: ProgressEvent) => void;
  onResult: (result: ScreenResult) => void;
  onError: (error: Error) => void;
  onCancelled: () => void;
}

/**
 * Run a streaming screening request. Returns an abort function. The terminal
 * `result` / `error` / `cancelled` events resolve the run; the caller's
 * watchdog handles stalls (this function does not time out on its own).
 */
export async function streamScreen(
  request: ScreenRequest,
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/screen/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(request),
      signal,
    });
  } catch (err) {
    if (signal.aborted) return handlers.onCancelled();
    throw err;
  }

  if (!response.ok) {
    // Surface HTTP-level rejections (422/429/503) before the stream starts.
    let message = `${response.status} ${response.statusText}`;
    let detail: unknown;
    try {
      const body = await response.json();
      detail = body?.detail;
      if (typeof detail === "string") message = detail;
    } catch {
      /* keep status message */
    }
    throw new ApiError(response.status, message, detail as never);
  }
  if (!response.body) throw new Error("Streaming response has no body");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseFrameParser();

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      const frames = parser.push(decoder.decode(value, { stream: true }));
      for (const frame of frames) {
        dispatchFrame(frame, handlers);
      }
    }
  } catch (err) {
    if (signal.aborted) return handlers.onCancelled();
    throw err;
  }
}

function dispatchFrame(frame: ParsedFrame, handlers: StreamHandlers): void {
  let payload: ProgressEvent;
  try {
    payload = JSON.parse(frame.data) as ProgressEvent;
  } catch {
    return; // Ignore comments/heartbeat frames without JSON data.
  }
  handlers.onEvent(payload);

  const kind = frame.event ?? payload.event;
  if (kind === "result") {
    const result = (payload.payload?.result ?? payload.payload) as ScreenResult;
    handlers.onResult(result);
  } else if (kind === "error") {
    handlers.onError(new Error(payload.message || "Screening run failed"));
  } else if (kind === "cancelled") {
    handlers.onCancelled();
  }
}
