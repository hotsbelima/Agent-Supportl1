import { describe, expect, it } from "vitest";

import {
  connectionTone,
  eventSummary,
  evidenceSourceLabel,
  incidentTextLabel,
  FIELD_SERVICE_OUTCOME_NOTE,
  observationState,
  playbackIncidentStatus,
  playbackVisibility,
  proposalTone,
  scenario2InvestigationActivities,
  STALE_PROPOSAL_NOTE,
  TIMELINE_PLAYBACK_INTERVAL_MS,
} from "../lib/presentation";
import { isStateRefreshEvent } from "../lib/recovery";
import {
  applicationEventFromFrame,
  createSseParser,
  type SseFrame,
} from "../lib/sse";
import type {
  ApplicationEventView,
  EvidenceView,
  Scenario2IngestionStateResponse,
} from "../lib/types";

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
      .toBe("Начата проверка: Проверка устройства");
    expect(eventSummary(event("tool.started"))).toBe("Начата системная проверка");
    expect(eventSummary(event("run.status_changed", { status: "ACTIVE" })))
      .toBe("Статус запуска → Активен");
    expect(
      eventSummary(
        event("observation.recorded", { source_type: "CMDB_SNAPSHOT" }),
      ),
    ).toBe("Сохранено наблюдение: Данные CMDB");
  });

  it("uses human-readable Russian labels for technical product values", () => {
    expect(evidenceSourceLabel("CMDB_SNAPSHOT")).toBe("Данные CMDB");
    expect(evidenceSourceLabel("ACCESS_LINK_DIAGNOSTIC")).toBe(
      "Диагностика канала доступа",
    );
    expect(incidentTextLabel("Payment terminal is unavailable.")).toBe(
      "Платёжный терминал недоступен.",
    );
    expect(incidentTextLabel("payment_gateway_timeout")).toBe(
      "Таймаут платёжного шлюза.",
    );
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

  it("keeps entity visibility aligned with the playback cursor", () => {
    const beforeApproval = playbackVisibility([
      {
        ...event("external.signal", {
          details: { site_id: "SITE-MSK-001" },
        }),
        seq: 1,
      },
      {
        ...event("observation.recorded", { evidence_id: "E-1" }),
        seq: 2,
      },
      {
        ...event("proposal.created", { proposal_id: "P-1" }),
        seq: 3,
      },
      {
        ...event("run.status_changed", { status: "WAITING_APPROVAL" }),
        seq: 4,
      },
    ]);

    expect([...beforeApproval.signalSites]).toEqual(["SITE-MSK-001"]);
    expect([...beforeApproval.evidenceIds]).toEqual(["E-1"]);
    expect([...beforeApproval.proposalIds]).toEqual(["P-1"]);
    expect(beforeApproval.approvalRequested).toBe(true);
    expect(beforeApproval.approvalDecided).toBe(false);
    expect(beforeApproval.approvalDecision).toBeNull();
    expect(beforeApproval.actionExecuted).toBe(false);
    expect(playbackIncidentStatus("ESCALATED", false)).toBe("OPEN");

    const afterExecution = playbackVisibility([
      { ...event("approval.decided", { decision: "APPROVED" }), seq: 5 },
      { ...event("action.executed", { proposal_id: "P-1" }), seq: 6 },
    ]);
    expect(afterExecution.approvalDecided).toBe(true);
    expect(afterExecution.approvalDecision).toBe("APPROVED");
    expect(afterExecution.actionExecuted).toBe(true);
    expect(playbackIncidentStatus("ESCALATED", true)).toBe("ESCALATED");
  });

  it("builds Scenario 2 human activity only from persisted signals, evidence and proposal state", () => {
    const state: Scenario2IngestionStateResponse = {
      run: {
        run_id: "RUN-1",
        tenant_id: "TENANT-8OCT",
        scenario_id: "scenario-2",
        status: "WAITING_APPROVAL",
        created_at: "2026-10-05T00:00:00Z",
        updated_at: "2026-10-05T00:00:30Z",
      },
      service_incidents: [],
      operational_signals: [],
      evidence: [
        {
          evidence_id: "E-LOCAL",
          tenant_id: "TENANT-8OCT",
          run_id: "RUN-1",
          source_type: "LOCAL_SERVICE_HEALTH",
          captured_at: "2026-10-05T00:00:20Z",
          entity_ids: ["SITE-KZN-017", "payment_gateway"],
          payload: {
            site_id: "SITE-KZN-017",
            service_key: "payment_gateway",
            network_health: "HEALTHY",
            local_service_health: "HEALTHY",
          },
          facts: [],
          expires_at: "2026-10-05T00:05:20Z",
        },
      ],
      major_incident_proposals: [
        {
          proposal_id: "MIP-1",
          tenant_id: "TENANT-8OCT",
          run_id: "RUN-1",
          correlation_key: "payment_gateway_timeout",
          service_key: "payment_gateway",
          affected_site_ids: ["SITE-KZN-017", "SITE-SAM-024"],
          dependency_id: "DEP-ACMEPAY-PAYMENTS",
          dependency_name: "AcmePay",
          action_type: "CREATE_MAJOR_INCIDENT",
          evidence_ids: ["E-LOCAL"],
          summary: "Cross-site payment timeouts",
          rationale: "Persisted evidence supports a shared dependency.",
          status: "PENDING_APPROVAL",
          created_at: "2026-10-05T00:00:25Z",
          updated_at: "2026-10-05T00:00:25Z",
        },
      ],
      major_incident_approvals: [],
      major_incident_executions: [],
      major_incidents: [],
      latest_event_seq: 5,
    };

    const activities = scenario2InvestigationActivities(
      [
        {
          ...event("external.signal", {
            source: "MONITORING",
            site_id: "SITE-SAM-024",
            service_key: "payment_gateway",
            safe_payload: { kind: "payment_timeout_rate" },
          }),
          seq: 1,
        },
        {
          ...event("external.signal", {
            source: "ITSM",
            site_id: "SITE-KZN-017",
            service_key: "payment_gateway",
            safe_payload: {
              kind: "user_ticket",
              impact: "payment_attempts_timing_out",
            },
          }),
          seq: 2,
        },
        {
          ...event("observation.recorded", {
            evidence_id: "E-LOCAL",
            source_type: "LOCAL_SERVICE_HEALTH",
          }),
          seq: 3,
        },
        {
          ...event("proposal.created", { proposal_id: "MIP-1" }),
          seq: 4,
        },
        {
          ...event("run.status_changed", { status: "WAITING_APPROVAL" }),
          seq: 5,
        },
      ],
      state,
    );

    expect(TIMELINE_PLAYBACK_INTERVAL_MS).toBe(5_000);
    expect(activities.map((item) => item.title)).toEqual([
      "Агент запросил подтверждение действия",
      "Агент выявил корреляцию между событиями",
      "Агент проверил локальную инфраструктуру",
      "Получена заявка пользователя: платёжные операции завершаются по таймауту на площадке SITE-KZN-017",
      "Получен сигнал мониторинга: повышенный уровень таймаутов платежей на площадке SITE-SAM-024",
    ]);
    expect(activities[1].detail).toContain("AcmePay");
    expect(activities[1].detail).toContain("SITE-KZN-017");
    expect(activities[1].detail).toContain("SITE-SAM-024");
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
      "Заявка на выездной сервис зарегистрирована.",
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
