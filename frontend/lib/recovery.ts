import type {
  ApplicationEventView,
  ConnectionState,
  RunStateResponse,
  TimelineResponse,
} from "./types";

export const TIMELINE_PAGE_LIMIT = 1000;
export const RECONNECT_DELAYS_MS = [500, 1000, 2000, 5000] as const;
export const OFFLINE_AFTER_FAILURES = 4;

export class TimelineGapError extends Error {
  constructor(
    readonly cursor: number,
    readonly receivedSeq: number,
  ) {
    super(
      `Timeline gap detected: expected seq ${cursor + 1}, received ${receivedSeq}.`,
    );
    this.name = "TimelineGapError";
  }
}

export class TimelineRunMismatchError extends Error {
  constructor(
    readonly expectedRunId: string,
    readonly receivedRunId: string,
  ) {
    super(
      `Timeline event belongs to ${receivedRunId}, expected ${expectedRunId}.`,
    );
    this.name = "TimelineRunMismatchError";
  }
}

export type TimelineAccumulator = {
  cursor: number;
  events: ApplicationEventView[];
};

export type ApplyEventResult =
  | {
      kind: "accepted";
      timeline: TimelineAccumulator;
      event: ApplicationEventView;
    }
  | {
      kind: "duplicate";
      timeline: TimelineAccumulator;
      event: ApplicationEventView;
    }
  | {
      kind: "gap";
      timeline: TimelineAccumulator;
      event: ApplicationEventView;
      error: TimelineGapError;
    };

export type TimelinePageReader = (
  runId: string,
  afterSeq: number,
  limit: number,
  signal?: AbortSignal,
) => Promise<TimelineResponse>;

export type RunStateReader = (
  runId: string,
  signal?: AbortSignal,
) => Promise<RunStateResponse>;

export function emptyTimeline(cursor = 0): TimelineAccumulator {
  if (!Number.isSafeInteger(cursor) || cursor < 0) {
    throw new Error("Timeline cursor must be a non-negative safe integer.");
  }
  return { cursor, events: [] };
}

function assertEventRun(
  runId: string,
  event: ApplicationEventView,
): void {
  if (event.run_id !== runId) {
    throw new TimelineRunMismatchError(runId, event.run_id);
  }
}

export function applyTimelineEvent(
  timeline: TimelineAccumulator,
  event: ApplicationEventView,
  runId: string,
): ApplyEventResult {
  assertEventRun(runId, event);

  if (!Number.isSafeInteger(event.seq) || event.seq < 1) {
    throw new Error("Persisted event seq must be a positive safe integer.");
  }

  if (event.seq <= timeline.cursor) {
    return {
      kind: "duplicate",
      timeline,
      event,
    };
  }

  if (event.seq > timeline.cursor + 1) {
    return {
      kind: "gap",
      timeline,
      event,
      error: new TimelineGapError(timeline.cursor, event.seq),
    };
  }

  return {
    kind: "accepted",
    timeline: {
      cursor: event.seq,
      events: [...timeline.events, event],
    },
    event,
  };
}

export function mergeTimelineEvents(
  timeline: TimelineAccumulator,
  events: readonly ApplicationEventView[],
  runId: string,
): TimelineAccumulator {
  let next = timeline;

  for (const event of events) {
    const result = applyTimelineEvent(next, event, runId);
    if (result.kind === "gap") {
      throw result.error;
    }
    next = result.timeline;
  }

  return next;
}

export async function fetchTimelinePages(options: {
  runId: string;
  afterSeq: number;
  readPage: TimelinePageReader;
  signal?: AbortSignal;
  pageLimit?: number;
}): Promise<TimelineAccumulator> {
  const {
    runId,
    afterSeq,
    readPage,
    signal,
    pageLimit = TIMELINE_PAGE_LIMIT,
  } = options;

  if (!Number.isSafeInteger(pageLimit) || pageLimit < 1 || pageLimit > 1000) {
    throw new Error("Timeline page limit must be between 1 and 1000.");
  }

  let collected = emptyTimeline(afterSeq);

  while (true) {
    const before = collected.cursor;
    const page = await readPage(runId, before, pageLimit, signal);

    if (page.run_id !== runId) {
      throw new TimelineRunMismatchError(runId, page.run_id);
    }

    collected = mergeTimelineEvents(collected, page.events, runId);

    if (page.events.length < pageLimit) {
      return collected;
    }

    if (collected.cursor === before) {
      throw new Error("Timeline pagination made no cursor progress.");
    }
  }
}

export async function bootstrapPersistedRun(options: {
  runId: string;
  readState: RunStateReader;
  readPage: TimelinePageReader;
  signal?: AbortSignal;
  pageLimit?: number;
}): Promise<{
  state: RunStateResponse;
  timeline: TimelineAccumulator;
}> {
  const { runId, readState, readPage, signal, pageLimit } = options;

  let state = await readState(runId, signal);
  const timeline = await fetchTimelinePages({
    runId,
    afterSeq: 0,
    readPage,
    signal,
    pageLimit,
  });

  if (state.latest_event_seq < timeline.cursor) {
    state = await readState(runId, signal);
  }

  return { state, timeline };
}

export async function prepareReconnect(options: {
  runId: string;
  cursor: number;
  readState: RunStateReader;
  readPage: TimelinePageReader;
  signal?: AbortSignal;
  pageLimit?: number;
}): Promise<{
  state: RunStateResponse;
  backfill: TimelineAccumulator;
}> {
  const {
    runId,
    cursor,
    readState,
    readPage,
    signal,
    pageLimit,
  } = options;

  let state = await readState(runId, signal);
  const backfill = await fetchTimelinePages({
    runId,
    afterSeq: cursor,
    readPage,
    signal,
    pageLimit,
  });

  if (state.latest_event_seq < backfill.cursor) {
    state = await readState(runId, signal);
  }

  return { state, backfill };
}

export function reconnectDelayMs(failureCount: number): number {
  if (!Number.isSafeInteger(failureCount) || failureCount < 1) {
    throw new Error("Reconnect failure count must be a positive integer.");
  }
  const index = Math.min(
    failureCount - 1,
    RECONNECT_DELAYS_MS.length - 1,
  );
  return RECONNECT_DELAYS_MS[index];
}

export function connectionStateForFailure(
  failureCount: number,
): ConnectionState {
  if (!Number.isSafeInteger(failureCount) || failureCount < 1) {
    throw new Error("Reconnect failure count must be a positive integer.");
  }
  return failureCount >= OFFLINE_AFTER_FAILURES
    ? "Offline/Unavailable"
    : "Reconnecting";
}

export function abortableDelay(
  delayMs: number,
  signal: AbortSignal,
): Promise<void> {
  if (!Number.isFinite(delayMs) || delayMs < 0) {
    return Promise.reject(new Error("Delay must be a finite non-negative value."));
  }
  if (signal.aborted) {
    return Promise.reject(new DOMException("Aborted", "AbortError"));
  }

  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, delayMs);

    function onAbort() {
      clearTimeout(timer);
      signal.removeEventListener("abort", onAbort);
      reject(new DOMException("Aborted", "AbortError"));
    }

    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export function isStateRefreshEvent(event: ApplicationEventView): boolean {
  return (
    event.event_type === "proposal.created" ||
    event.event_type === "approval.decided" ||
    event.event_type === "action.executed" ||
    event.event_type === "run.status_changed"
  );
}

export type DecisionRecoveryStatus =
  | "persisted"
  | "still-pending"
  | "missing";

export function decisionRecoveryStatus(
  state: RunStateResponse,
  proposalId: string,
): DecisionRecoveryStatus {
  const proposal = state.proposals.find(
    (item) => item.proposal_id === proposalId,
  );
  if (!proposal) return "missing";

  const approvalExists = state.approvals.some(
    (item) => item.proposal_id === proposalId,
  );

  if (
    approvalExists &&
    ["REJECTED", "STALE", "EXECUTED"].includes(proposal.status)
  ) {
    return "persisted";
  }

  return proposal.status === "PENDING_APPROVAL"
    ? "still-pending"
    : "missing";
}

export function replayNotice(replayed: boolean): string {
  return replayed
    ? "Persisted decision replayed; no duplicate action was created."
    : "Decision recorded in authoritative persisted state.";
}
