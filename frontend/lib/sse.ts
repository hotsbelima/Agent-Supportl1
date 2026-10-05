import { ApiClientError, apiUrl, tenantHeaders } from "./api";
import type { ApplicationEventView } from "./types";

export type SseFrame = {
  id?: string;
  event?: string;
  data?: string;
  comment?: string;
};

export type SseParser = {
  push(chunk: string): void;
  flush(): void;
};

function parseBlock(block: string): SseFrame | null {
  const frame: SseFrame = {};
  const data: string[] = [];
  const comments: string[] = [];
  for (const line of block.split("\n")) {
    if (!line) continue;
    if (line.startsWith(":")) {
      comments.push(line.slice(1).trimStart());
      continue;
    }
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "id") frame.id = value;
    if (field === "event") frame.event = value;
    if (field === "data") data.push(value);
  }
  if (comments.length) frame.comment = comments.join("\n");
  if (data.length) frame.data = data.join("\n");
  return Object.keys(frame).length ? frame : null;
}

export function createSseParser(
  onFrame: (frame: SseFrame) => void,
): SseParser {
  let buffer = "";
  const drain = () => {
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const frame = parseBlock(block);
      if (frame) onFrame(frame);
      boundary = buffer.indexOf("\n\n");
    }
  };
  return {
    push(chunk: string) {
      buffer += chunk.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
      drain();
    },
    flush() {
      drain();
      if (buffer.trim()) {
        const frame = parseBlock(buffer);
        if (frame) onFrame(frame);
      }
      buffer = "";
    },
  };
}

function isEventView(value: unknown): value is ApplicationEventView {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ApplicationEventView>;
  return (
    typeof candidate.event_id === "string" &&
    typeof candidate.tenant_id === "string" &&
    typeof candidate.run_id === "string" &&
    Number.isInteger(candidate.seq) &&
    typeof candidate.event_type === "string" &&
    typeof candidate.occurred_at === "string" &&
    !!candidate.payload &&
    typeof candidate.payload === "object" &&
    !Array.isArray(candidate.payload)
  );
}

export function applicationEventFromFrame(
  frame: SseFrame,
): ApplicationEventView | null {
  if (frame.comment !== undefined && !frame.data) return null;
  if (frame.event !== "application.event" || !frame.data || !frame.id) {
    return null;
  }
  const id = Number(frame.id);
  if (!Number.isSafeInteger(id) || id < 0) {
    throw new Error("Invalid SSE event id.");
  }
  const payload: unknown = JSON.parse(frame.data);
  if (!isEventView(payload)) {
    throw new Error("Invalid application.event payload.");
  }
  if (payload.seq !== id) {
    throw new Error("SSE event id does not match persisted sequence.");
  }
  return payload;
}

export async function streamRunEvents(options: {
  runId: string;
  afterSeq: number;
  lastEventId?: number;
  signal: AbortSignal;
  onOpen: () => void;
  onEvent: (event: ApplicationEventView) => void;
  onHeartbeat?: () => void;
}): Promise<void> {
  const params = new URLSearchParams({ after_seq: String(options.afterSeq) });
  const response = await fetch(
    apiUrl(
      `/api/v1/runs/${encodeURIComponent(
        options.runId,
      )}/events/stream?${params}`,
    ),
    {
      method: "GET",
      cache: "no-store",
      signal: options.signal,
      headers: tenantHeaders({
        Accept: "text/event-stream",
        ...(options.lastEventId === undefined
          ? {}
          : { "Last-Event-ID": String(options.lastEventId) }),
      }),
    },
  );
  if (!response.ok) throw await ApiClientError.fromResponse(response);
  if (!response.body) throw new Error("SSE response body is unavailable.");

  options.onOpen();
  const decoder = new TextDecoder();
  const parser = createSseParser((frame) => {
    if (frame.comment !== undefined && !frame.data) {
      options.onHeartbeat?.();
      return;
    }
    const event = applicationEventFromFrame(frame);
    if (event) options.onEvent(event);
  });

  const reader = response.body.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.flush();
  } catch (error) {
    try {
      await reader.cancel();
    } catch {
      // The original stream/parser error is authoritative.
    }
    throw error;
  } finally {
    reader.releaseLock();
  }
}
