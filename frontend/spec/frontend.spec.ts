import { describe, expect, it } from "vitest";

import {
  connectionTone,
  eventSummary,
  FIELD_SERVICE_OUTCOME_NOTE,
  proposalTone,
} from "../lib/presentation";
import {
  applicationEventFromFrame,
  createSseParser,
  type SseFrame,
} from "../lib/sse";
import type { ApplicationEventView } from "../lib/types";

function event(
  eventType: string,
  payload: ApplicationEventView["payload"] = {},
): ApplicationEventView {
  return {
    event_id: "EVENT-1",
    tenant_id: "TENANT-8OCT",
    run_id: "RUN-1",
    seq: 1,
    event_type: eventType,
    occurred_at: "2026-10-05T00:00:00Z",
    payload,
  };
}

describe("operational presentation", () => {
  it("uses persisted details without inventing missing fields", () => {
    expect(eventSummary(event("tool.started", { tool_name: "get_device" })))
      .toBe("Tool started: get_device");
    expect(eventSummary(event("tool.started"))).toBe("Tool started");
    expect(eventSummary(event("run.status_changed", { status: "ACTIVE" })))
      .toBe("Run status changed → ACTIVE");
  });

  it("keeps important states visually distinct", () => {
    expect(proposalTone("STALE")).toBe("stale");
    expect(proposalTone("REJECTED")).toBe("rejected");
    expect(proposalTone("EXECUTED")).toBe("executed");
    expect(connectionTone("Live")).toBe("live");
    expect(connectionTone("Offline/Unavailable")).toBe("offline");
  });

  it("never presents a registered work order as a completed repair", () => {
    expect(FIELD_SERVICE_OUTCOME_NOTE).toBe(
      "Onsite field-service work order registered. This is not proof of repair.",
    );
    expect(FIELD_SERVICE_OUTCOME_NOTE.toLowerCase()).not.toContain(
      "incident resolved",
    );
  });
});

describe("streaming fetch SSE parser", () => {
  it("handles split chunks and heartbeat comments", () => {
    const frames: SseFrame[] = [];
    const parser = createSseParser((frame) => frames.push(frame));

    parser.push(": keep");
    parser.push("alive\n\nid: 4\nevent: application.event\ndata: ");
    parser.push(
      '{"event_id":"E4","tenant_id":"T","run_id":"R","seq":4,' +
        '"event_type":"external.signal","occurred_at":"2026-10-05T00:00:00Z",' +
        '"payload":{"signal_type":"incident"}}\n\n',
    );
    parser.flush();

    expect(frames).toHaveLength(2);
    expect(frames[0]).toEqual({ comment: "keepalive" });
    expect(applicationEventFromFrame(frames[0])).toBeNull();
    expect(applicationEventFromFrame(frames[1])?.seq).toBe(4);
  });

  it("rejects a transport id that disagrees with persisted seq", () => {
    expect(() =>
      applicationEventFromFrame({
        id: "5",
        event: "application.event",
        data: JSON.stringify({
          event_id: "E4",
          tenant_id: "T",
          run_id: "R",
          seq: 4,
          event_type: "external.signal",
          occurred_at: "2026-10-05T00:00:00Z",
          payload: {},
        }),
      }),
    ).toThrow("does not match");
  });
});
