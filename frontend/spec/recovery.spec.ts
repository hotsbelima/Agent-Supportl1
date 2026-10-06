import { describe, expect, it, vi } from "vitest";

import {
  abortableDelay,
  applyTimelineEvent,
  bootstrapPersistedRun,
  connectionStateForFailure,
  decisionRecoveryStatus,
  emptyTimeline,
  fetchTimelinePages,
  isStateRefreshEvent,
  mergeTimelineEvents,
  nextTransportFailure,
  prepareReconnect,
  reconnectDelayMs,
  replayNotice,
  TimelineGapError,
} from "../lib/recovery";
import type {
  ApplicationEventView,
  RunStateResponse,
  TimelineResponse,
} from "../lib/types";

function event(
  seq: number,
  runId = "RUN-1",
  eventType = "external.signal",
): ApplicationEventView {
  return {
    event_id: `EVENT-${seq}`,
    tenant_id: "TENANT-8OCT",
    run_id: runId,
    seq,
    event_type: eventType,
    occurred_at: `2026-10-05T00:00:${String(seq).padStart(2, "0")}Z`,
    payload: { seq },
  };
}

function state(
  latestEventSeq: number,
  proposalStatus = "PENDING_APPROVAL",
): RunStateResponse {
  return {
    run: {
      run_id: "RUN-1",
      tenant_id: "TENANT-8OCT",
      scenario_id: "scenario-1",
      status: "ACTIVE",
      created_at: "2026-10-05T00:00:00Z",
      updated_at: "2026-10-05T00:00:00Z",
    },
    incidents: [
      {
        incident_id: "INC-1",
        tenant_id: "TENANT-8OCT",
        run_id: "RUN-1",
        site_id: "SITE-1",
        reported_device_id: "POS-1",
        symptom: "offline",
        status: proposalStatus === "EXECUTED" ? "ESCALATED" : "OPEN",
        created_at: "2026-10-05T00:00:00Z",
        updated_at: "2026-10-05T00:00:00Z",
      },
    ],
    evidence: [],
    proposals: [
      {
        proposal_id: "PROP-1",
        tenant_id: "TENANT-8OCT",
        run_id: "RUN-1",
        incident_id: "INC-1",
        device_id: "POS-1",
        diagnosis: "LOCAL_ACCESS_LINK_FAILURE",
        action_type: "ONSITE_FIELD_VISIT",
        evidence_ids: [],
        rationale: "Persisted proposal.",
        status: proposalStatus,
        created_at: "2026-10-05T00:00:00Z",
        updated_at: "2026-10-05T00:00:00Z",
      },
    ],
    approvals:
      proposalStatus === "PENDING_APPROVAL"
        ? []
        : [
            {
              approval_id: "APR-1",
              tenant_id: "TENANT-8OCT",
              run_id: "RUN-1",
              proposal_id: "PROP-1",
              decision:
                proposalStatus === "REJECTED" ? "REJECTED" : "APPROVED",
              decided_at: "2026-10-05T00:00:01Z",
              decided_by: "operator",
            },
          ],
    executed_actions:
      proposalStatus === "EXECUTED"
        ? [
            {
              action_id: "ACTION-1",
              tenant_id: "TENANT-8OCT",
              run_id: "RUN-1",
              proposal_id: "PROP-1",
              incident_id: "INC-1",
              device_id: "POS-1",
              action_type: "ONSITE_FIELD_VISIT",
              executed_at: "2026-10-05T00:00:02Z",
            },
          ]
        : [],
    work_orders:
      proposalStatus === "EXECUTED"
        ? [
            {
              work_order_id: "WO-1",
              tenant_id: "TENANT-8OCT",
              run_id: "RUN-1",
              proposal_id: "PROP-1",
              incident_id: "INC-1",
              device_id: "POS-1",
              site_id: "SITE-1",
              attachment_id: "ATT-1",
              switch_id: "SW-1",
              port_id: "Gi1/0/18",
              created_at: "2026-10-05T00:00:02Z",
            },
          ]
        : [],
    latest_event_seq: latestEventSeq,
  };
}

function page(
  events: ApplicationEventView[],
  runId = "RUN-1",
): TimelineResponse {
  return {
    run_id: runId,
    events,
    next_cursor: events.at(-1)?.seq ?? 0,
  };
}

describe("timeline cursor and live event classification", () => {
  it("accepts exactly cursor + 1", () => {
    const result = applyTimelineEvent(emptyTimeline(3), event(4), "RUN-1");

    expect(result.kind).toBe("accepted");
    expect(result.timeline.cursor).toBe(4);
    expect(result.timeline.events.map((item) => item.seq)).toEqual([4]);
  });

  it("ignores duplicate or replayed seq <= cursor", () => {
    const initial = {
      cursor: 4,
      events: [event(1), event(2), event(3), event(4)],
    };

    const replay = applyTimelineEvent(initial, event(4), "RUN-1");
    const older = applyTimelineEvent(initial, event(2), "RUN-1");

    expect(replay.kind).toBe("duplicate");
    expect(older.kind).toBe("duplicate");
    expect(replay.timeline).toBe(initial);
    expect(older.timeline).toBe(initial);
  });

  it("detects a sequence gap instead of silently accepting a later frame", () => {
    const result = applyTimelineEvent(emptyTimeline(4), event(7), "RUN-1");

    expect(result.kind).toBe("gap");
    if (result.kind !== "gap") throw new Error("expected gap");
    expect(result.error).toBeInstanceOf(TimelineGapError);
    expect(result.error.cursor).toBe(4);
    expect(result.error.receivedSeq).toBe(7);
    expect(result.timeline.cursor).toBe(4);
  });

  it("rejects cross-run events at the client boundary", () => {
    expect(() =>
      applyTimelineEvent(emptyTimeline(0), event(1, "RUN-2"), "RUN-1"),
    ).toThrow("expected RUN-1");
  });

  it("deduplicates replay when merging backfill with existing timeline", () => {
    const initial = {
      cursor: 3,
      events: [event(1), event(2), event(3)],
    };

    const merged = mergeTimelineEvents(
      initial,
      [event(3), event(4), event(5)],
      "RUN-1",
    );

    expect(merged.cursor).toBe(5);
    expect(merged.events.map((item) => item.seq)).toEqual([1, 2, 3, 4, 5]);
  });
});

describe("persisted timeline pagination and bootstrap", () => {
  it("paginates until a short page and returns the last accepted persisted cursor", async () => {
    const calls: number[] = [];
    const readPage = vi.fn(
      async (
        runId: string,
        afterSeq: number,
        limit: number,
      ): Promise<TimelineResponse> => {
        expect(runId).toBe("RUN-1");
        expect(limit).toBe(2);
        calls.push(afterSeq);
        if (afterSeq === 0) return page([event(1), event(2)]);
        if (afterSeq === 2) return page([event(3), event(4)]);
        return page([event(5)]);
      },
    );

    const result = await fetchTimelinePages({
      runId: "RUN-1",
      afterSeq: 0,
      readPage,
      pageLimit: 2,
    });

    expect(calls).toEqual([0, 2, 4]);
    expect(result.cursor).toBe(5);
    expect(result.events.map((item) => item.seq)).toEqual([1, 2, 3, 4, 5]);
  });

  it("fails if a full pagination page cannot advance the persisted cursor", async () => {
    const readPage = vi.fn(async () =>
      page([event(2), event(2)]),
    );

    await expect(
      fetchTimelinePages({
        runId: "RUN-1",
        afterSeq: 2,
        readPage,
        pageLimit: 2,
      }),
    ).rejects.toThrow("made no cursor progress");
  });

  it("reload bootstrap reconstructs state and the full timeline from backend only", async () => {
    const readState = vi.fn(async () => state(5));
    const readPage = vi.fn(
      async (
        _runId: string,
        afterSeq: number,
      ): Promise<TimelineResponse> =>
        afterSeq === 0
          ? page([event(1), event(2)])
          : afterSeq === 2
            ? page([event(3), event(4)])
            : page([event(5)]),
    );

    const result = await bootstrapPersistedRun({
      runId: "RUN-1",
      readState,
      readPage,
      pageLimit: 2,
    });

    expect(result.state.latest_event_seq).toBe(5);
    expect(result.timeline.cursor).toBe(5);
    expect(result.timeline.events.map((item) => item.seq)).toEqual([
      1, 2, 3, 4, 5,
    ]);
  });

  it("re-reads authoritative state if persisted timeline advanced after first state read", async () => {
    const reads: string[] = [];
    const readState = vi
      .fn()
      .mockImplementationOnce(async () => {
        reads.push("state:3");
        return state(3);
      })
      .mockImplementationOnce(async () => {
        reads.push("state:4");
        return state(4);
      });

    const readPage = vi.fn(async () => {
      reads.push("timeline:4");
      return page([event(1), event(2), event(3), event(4)]);
    });

    const result = await bootstrapPersistedRun({
      runId: "RUN-1",
      readState,
      readPage,
    });

    expect(reads).toEqual(["state:3", "timeline:4", "state:4"]);
    expect(result.state.latest_event_seq).toBe(4);
    expect(result.timeline.cursor).toBe(4);
  });
});

describe("reconnect preparation and backoff", () => {
  it("paginates reconnect backfill until the persisted tail is complete", async () => {
    const calls: number[] = [];
    const readState = vi.fn(async () => state(8));
    const readPage = vi.fn(
      async (
        _runId: string,
        afterSeq: number,
      ): Promise<TimelineResponse> => {
        calls.push(afterSeq);
        if (afterSeq === 4) return page([event(5), event(6)]);
        if (afterSeq === 6) return page([event(7), event(8)]);
        return page([]);
      },
    );

    const result = await prepareReconnect({
      runId: "RUN-1",
      cursor: 4,
      readState,
      readPage,
      pageLimit: 2,
    });

    expect(calls).toEqual([4, 6, 8]);
    expect(result.backfill.cursor).toBe(8);
    expect(result.backfill.events.map((item) => item.seq)).toEqual([
      5, 6, 7, 8,
    ]);
  });

  it("refreshes authoritative state, backfills after cursor, then refreshes state again if backfill is newer", async () => {
    const order: string[] = [];
    const readState = vi
      .fn()
      .mockImplementationOnce(async () => {
        order.push("state:4");
        return state(4);
      })
      .mockImplementationOnce(async () => {
        order.push("state:6");
        return state(6);
      });

    const readPage = vi.fn(
      async (
        _runId: string,
        afterSeq: number,
      ): Promise<TimelineResponse> => {
        order.push(`timeline:${afterSeq}`);
        return page([event(5), event(6)]);
      },
    );

    const result = await prepareReconnect({
      runId: "RUN-1",
      cursor: 4,
      readState,
      readPage,
    });

    expect(order).toEqual(["state:4", "timeline:4", "state:6"]);
    expect(result.state.latest_event_seq).toBe(6);
    expect(result.backfill.cursor).toBe(6);
    expect(result.backfill.events.map((item) => item.seq)).toEqual([5, 6]);
  });

  it("uses bounded exponential backoff with a five-second cap", () => {
    expect([
      reconnectDelayMs(1),
      reconnectDelayMs(2),
      reconnectDelayMs(3),
      reconnectDelayMs(4),
      reconnectDelayMs(5),
      reconnectDelayMs(99),
    ]).toEqual([500, 1000, 2000, 5000, 5000, 5000]);
  });

  it("carries repeated transport failures forward instead of resetting on header open", () => {
    expect(nextTransportFailure(0)).toEqual({
      failureCount: 1,
      connection: "Reconnecting",
      delayMs: 500,
    });
    expect(nextTransportFailure(3)).toEqual({
      failureCount: 4,
      connection: "Offline/Unavailable",
      delayMs: 5000,
    });
  });

  it("transitions from Reconnecting to Offline/Unavailable after repeated failures", () => {
    expect(connectionStateForFailure(1)).toBe("Reconnecting");
    expect(connectionStateForFailure(2)).toBe("Reconnecting");
    expect(connectionStateForFailure(3)).toBe("Reconnecting");
    expect(connectionStateForFailure(4)).toBe("Offline/Unavailable");
    expect(connectionStateForFailure(8)).toBe("Offline/Unavailable");
  });

  it("abort stops a pending reconnect delay", async () => {
    const controller = new AbortController();
    const pending = abortableDelay(5000, controller.signal);
    controller.abort();

    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("decision response recovery", () => {
  it("recognizes an authoritative committed Approve after its HTTP response was lost", () => {
    expect(decisionRecoveryStatus(state(8, "EXECUTED"), "PROP-1")).toBe(
      "persisted",
    );
  });

  it("does not confirm EXECUTED when the required action/work-order artifacts are missing", () => {
    const inconsistent = state(8, "EXECUTED");
    inconsistent.work_orders = [];
    expect(decisionRecoveryStatus(inconsistent, "PROP-1")).toBe(
      "inconsistent",
    );
  });

  it("does not confirm a terminal decision while the run is not ACTIVE", () => {
    const inconsistent = state(8, "EXECUTED");
    inconsistent.run.status = "WAITING_APPROVAL";
    expect(decisionRecoveryStatus(inconsistent, "PROP-1")).toBe(
      "inconsistent",
    );
  });

  it("recognizes an authoritative committed Reject after its HTTP response was lost", () => {
    expect(decisionRecoveryStatus(state(7, "REJECTED"), "PROP-1")).toBe(
      "persisted",
    );
  });

  it("keeps retry available if authoritative state still says pending", () => {
    expect(
      decisionRecoveryStatus(state(6, "PENDING_APPROVAL"), "PROP-1"),
    ).toBe("still-pending");
  });

  it("reports missing when the proposal cannot be confirmed", () => {
    const missing = state(3);
    missing.proposals = [];
    expect(decisionRecoveryStatus(missing, "PROP-1")).toBe("missing");
  });

  it("refreshes authoritative state on tool.finished because evidence is persisted in that transaction", () => {
    expect(isStateRefreshEvent(event(4, "RUN-1", "tool.finished"))).toBe(true);
    expect(isStateRefreshEvent(event(4, "RUN-1", "tool.started"))).toBe(false);
    expect(isStateRefreshEvent(event(4, "RUN-1", "finding.recorded"))).toBe(false);
  });

  it("surfaces idempotent replay without claiming duplicate execution", () => {
    expect(replayNotice(true)).toContain("повторное действие не создавалось");
    expect(replayNotice(false)).toContain("авторитетном состоянии продукта");
  });
});
