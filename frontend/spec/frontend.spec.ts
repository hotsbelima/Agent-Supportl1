import { describe, expect, it } from "vitest";

import {
  connectionTone,
  eventSummary,
  FIELD_SERVICE_OUTCOME_NOTE,
  observationState,
  proposalTone,
  STALE_PROPOSAL_NOTE,
} from "../lib/presentation";
import { isStateRefreshEvent } from "../lib/recovery";
import {
  applicationEventFromFrame,
  createSseParser,
  type SseFrame,
} from "../lib/sse";
import type { ApplicationEventView, EvidenceView } from "../lib/types";

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
      .toBe("Запущен инструмент: get_device");
    expect(eventSummary(event("tool.started"))).toBe("Запущен инструмент");
    expect(eventSummary(event("run.status_changed", { status: "ACTIVE" })))
      .toBe("Статус запуска → Активен");
    expect(
      eventSummary(
        event("observation.recorded", { source_type: "CMDB_SNAPSHOT" }),
      ),
    ).toBe("Сохранено наблюдение: CMDB_SNAPSHOT");
  });

  it("refreshes authoritative state when a Product observation arrives", () => {
    expect(isStateRefreshEvent(event("observation.recorded"))).toBe(true);
    expect(isStateRefreshEvent(event("external.signal"))).toBe(false);
  });

  it("shows safe observation state when the typed evidence has one", () => {
    const base: EvidenceView = {
      evidence_id: "E-1",
      tenant_id: "TENANT-8OCT",
      run_id: "RUN-1",
      source_type: "ACCESS_LINK_DIAGNOSTIC",
      captured_at: "2026-10-05T00:00:00Z",
      entity_ids: ["ATT-1"],
      payload: { operational_state: "DOWN" },
      facts: [],
      expires_at: null,
    };
    expect(observationState(base)).toBe("DOWN");
    expect(
      observationState({
        ...base,
        source_type: "KB_ARTICLE",
        payload: { approved: true },
      }),
    ).toBe("APPROVED");
    expect(
      observationState({
        ...base,
        source_type: "CMDB_SNAPSHOT",
        payload: { site_id: "SITE-1" },
      }),
    ).toBeNull();
  });

  it("keeps important states visually distinct", () => {
    expect(proposalTone("STALE")).toBe("stale");
    expect(proposalTone("REJECTED")).toBe("rejected");
    expect(proposalTone("EXECUTED")).toBe("executed");
    expect(connectionTone("Live")).toBe("live");
    expect(connectionTone("Offline/Unavailable")).toBe("offline");
  });

  it("renders stale approval as zero execution rather than a failed repair", () => {
    expect(STALE_PROPOSAL_NOTE).toContain("Действие выездного сервиса не создавалось");
    expect(STALE_PROPOSAL_NOTE.toLowerCase()).not.toContain("отремонтирован");
    expect(STALE_PROPOSAL_NOTE.toLowerCase()).not.toContain("закрыт");
  });

  it("never presents a registered work order as a completed repair", () => {
    expect(FIELD_SERVICE_OUTCOME_NOTE).toBe(
      "Заявка на выездной сервис зарегистрирована. Это ещё не подтверждает ремонт устройства.",
    );
    expect(FIELD_SERVICE_OUTCOME_NOTE.toLowerCase()).not.toContain(
      "инцидент закрыт",
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
