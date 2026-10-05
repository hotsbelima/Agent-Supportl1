"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  decideProposal,
  displayApiError,
  getRunState,
  getRunTimeline,
  isRetryableApiFailure,
} from "@/lib/api";
import {
  abortableDelay,
  applyTimelineEvent,
  bootstrapPersistedRun,
  connectionStateForFailure,
  decisionRecoveryStatus,
  emptyTimeline,
  isStateRefreshEvent,
  mergeTimelineEvents,
  nextTransportFailure,
  prepareReconnect,
  reconnectDelayMs,
  replayNotice,
  TimelineGapError,
  type TimelineAccumulator,
} from "@/lib/recovery";
import {
  connectionTone,
  eventSummary,
  FIELD_SERVICE_OUTCOME_NOTE,
  formatTimestamp,
  proposalTone,
} from "@/lib/presentation";
import { streamRunEvents } from "@/lib/sse";
import type {
  ApplicationEventView,
  ConnectionState,
  ProposalView,
  RunStateResponse,
} from "@/lib/types";

const DEMO_OPERATOR = "portfolio-demo-operator";

function StatusBadge({
  value,
  tone = "neutral",
}: {
  value: string;
  tone?: string;
}) {
  return (
    <span className="status-badge" data-tone={tone}>
      {value}
    </span>
  );
}

function EmptyPanel({ children }: { children: ReactNode }) {
  return <div className="empty-panel">{children}</div>;
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function recoveryMessage(error: unknown): string {
  if (error instanceof TimelineGapError) {
    return "Timeline gap detected; recovering missing persisted events.";
  }
  if (error instanceof Error && error.message === "Live event stream closed.") {
    return "Live event stream closed; reconnecting from persisted state.";
  }
  return displayApiError(error);
}

export function RunConsole({ runId }: { runId: string }) {
  const [state, setState] = useState<RunStateResponse | null>(null);
  const [events, setEvents] = useState<ApplicationEventView[]>([]);
  const [connection, setConnection] =
    useState<ConnectionState>("Reconnecting");
  const [loading, setLoading] = useState(true);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [decision, setDecision] = useState<{
    proposalId: string;
    verb: "approve" | "reject";
  } | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [decisionNotice, setDecisionNotice] = useState<string | null>(null);

  const timelineByRunRef = useRef(new Map<string, TimelineAccumulator>());
  const cursorByRunRef = useRef(new Map<string, number>());
  const stateSeqByRunRef = useRef(new Map<string, number>());

  const publishState = useCallback(
    (current: RunStateResponse) => {
      const previousSeq = stateSeqByRunRef.current.get(runId) ?? -1;
      if (current.latest_event_seq >= previousSeq) {
        stateSeqByRunRef.current.set(runId, current.latest_event_seq);
        setState(current);
      }
      return current;
    },
    [runId],
  );

  const refreshState = useCallback(
    async (signal?: AbortSignal) => {
      const current = await getRunState(runId, signal);
      return publishState(current);
    },
    [publishState, runId],
  );

  useEffect(() => {
    const controller = new AbortController();
    let mounted = true;
    let failureCount = 0;
    let needsRecovery = false;

    const readState = (
      requestedRunId: string,
      signal?: AbortSignal,
    ) => getRunState(requestedRunId, signal);
    const readPage = (
      requestedRunId: string,
      afterSeq: number,
      limit: number,
      signal?: AbortSignal,
    ) => getRunTimeline(requestedRunId, afterSeq, limit, signal);

    function currentTimeline(): TimelineAccumulator {
      return timelineByRunRef.current.get(runId) ?? emptyTimeline(
        cursorByRunRef.current.get(runId) ?? 0,
      );
    }

    function publishTimeline(next: TimelineAccumulator) {
      timelineByRunRef.current.set(runId, next);
      cursorByRunRef.current.set(runId, next.cursor);
      if (mounted) setEvents(next.events);
    }

    async function runSession() {
      setLoading(true);
      setPageError(null);
      setStreamError(null);
      setConnection("Reconnecting");
      setDecisionError(null);
      setDecisionNotice(null);

      timelineByRunRef.current.set(runId, emptyTimeline());
      cursorByRunRef.current.set(runId, 0);
      stateSeqByRunRef.current.set(runId, -1);

      while (!controller.signal.aborted) {
        try {
          const bootstrapped = await bootstrapPersistedRun({
            runId,
            readState,
            readPage,
            signal: controller.signal,
          });
          if (!mounted) return;

          publishState(bootstrapped.state);
          publishTimeline(bootstrapped.timeline);
          failureCount = 0;
          setPageError(null);
          setLoading(false);
          break;
        } catch (error) {
          if (
            !mounted ||
            controller.signal.aborted ||
            isAbortError(error)
          ) {
            return;
          }

          if (!isRetryableApiFailure(error)) {
            setLoading(false);
            setConnection("Offline/Unavailable");
            setPageError(displayApiError(error));
            return;
          }

          const failure = nextTransportFailure(failureCount);
          failureCount = failure.failureCount;
          setConnection(failure.connection);
          setPageError(
            `${displayApiError(error)} Retrying persisted run state…`,
          );

          try {
            await abortableDelay(failure.delayMs, controller.signal);
          } catch (delayError) {
            if (isAbortError(delayError)) return;
            throw delayError;
          }
        }
      }

      while (!controller.signal.aborted) {
        try {
          if (needsRecovery) {
            setConnection(connectionStateForFailure(failureCount));
            await abortableDelay(
              reconnectDelayMs(failureCount),
              controller.signal,
            );

            const cursor = cursorByRunRef.current.get(runId) ?? 0;
            const recovered = await prepareReconnect({
              runId,
              cursor,
              readState,
              readPage,
              signal: controller.signal,
            });
            if (!mounted) return;

            const merged = mergeTimelineEvents(
              currentTimeline(),
              recovered.backfill.events,
              runId,
            );
            publishState(recovered.state);
            publishTimeline(merged);
          }

          const cursor = cursorByRunRef.current.get(runId) ?? 0;
          await streamRunEvents({
            runId,
            afterSeq: cursor,
            lastEventId: needsRecovery ? cursor : undefined,
            signal: controller.signal,
            onOpen: () => {
              if (!mounted) return;
              setConnection("Live");
              setStreamError(null);
            },
            onHeartbeat: () => {
              failureCount = 0;
            },
            onEvent: (event) => {
              if (!mounted) return;

              const result = applyTimelineEvent(
                currentTimeline(),
                event,
                runId,
              );

              if (result.kind === "duplicate") {
                failureCount = 0;
                return;
              }
              if (result.kind === "gap") {
                throw result.error;
              }

              failureCount = 0;
              publishTimeline(result.timeline);

              if (isStateRefreshEvent(event)) {
                void refreshState(controller.signal).catch(() => {
                  // Reconnect/backfill remains the recovery path if the
                  // authoritative state refresh is temporarily unavailable.
                });
              }
            },
          });

          if (!controller.signal.aborted) {
            throw new Error("Live event stream closed.");
          }
        } catch (error) {
          if (
            !mounted ||
            controller.signal.aborted ||
            isAbortError(error)
          ) {
            return;
          }

          const failure = nextTransportFailure(failureCount);
          failureCount = failure.failureCount;
          needsRecovery = true;
          setConnection(failure.connection);
          setStreamError(recoveryMessage(error));
        }
      }
    }

    void runSession();

    return () => {
      mounted = false;
      controller.abort();
    };
  }, [publishState, refreshState, runId]);

  const incident = state?.incidents[0] ?? null;
  const lastSeq = events.at(-1)?.seq ?? 0;

  const latestProposal: ProposalView | null = state?.proposals.length
    ? [...state.proposals]
        .sort((a, b) => a.created_at.localeCompare(b.created_at))
        .at(-1) ?? null
    : null;

  async function handleDecision(
    proposal: ProposalView,
    verb: "approve" | "reject",
  ) {
    if (decision) return;

    setDecision({ proposalId: proposal.proposal_id, verb });
    setDecisionError(null);
    setDecisionNotice(null);

    try {
      const result = await decideProposal(
        runId,
        proposal.proposal_id,
        verb,
        DEMO_OPERATOR,
      );
      setDecisionNotice(replayNotice(result.replayed));

      try {
        await refreshState();
      } catch {
        setDecisionError(
          "Decision was recorded, but the full state refresh is temporarily unavailable. Reconnect will synchronize authoritative state.",
        );
      }
    } catch (error) {
      try {
        const recovered = await refreshState();
        const recovery = decisionRecoveryStatus(
          recovered,
          proposal.proposal_id,
        );

        if (recovery === "persisted") {
          setDecisionNotice(
            "Decision response was interrupted; authoritative persisted state was recovered.",
          );
          setDecisionError(null);
        } else if (recovery === "still-pending") {
          setDecisionError(
            `${displayApiError(error)} Persisted state still shows this proposal as pending; retrying the same decision is safe.`,
          );
        } else if (recovery === "inconsistent") {
          setDecisionError(
            "Decision response was interrupted and persisted state is internally inconsistent, so execution is not being presented as confirmed.",
          );
        } else {
          setDecisionError(
            "Decision response was interrupted and the proposal could not be confirmed in authoritative state.",
          );
        }
      } catch {
        setDecisionError(
          "Decision result could not be confirmed. Reconnect will recover authoritative state; retrying the same decision remains idempotent.",
        );
      }
    } finally {
      setDecision(null);
    }
  }

  if (loading) {
    return (
      <main className="console-shell">
        <div className="console-loading">
          <span className="spinner" aria-hidden="true" />
          <strong>Loading persisted run</strong>
          <span>{runId}</span>
          {pageError ? <span role="status">{pageError}</span> : null}
        </div>
      </main>
    );
  }

  if (!state) {
    return (
      <main className="console-shell">
        <div className="fatal-card">
          <p className="eyebrow">Run unavailable</p>
          <h1>Operational state could not be loaded</h1>
          <p>{pageError ?? "The product API did not return run state."}</p>
          <Link className="secondary-button" href="/">
            Back to Scenario 1
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="console-shell">
      <header className="run-header">
        <div className="brand-lockup">
          <Link href="/" className="brand-mark" aria-label="Back to home">
            8O
          </Link>
          <div>
            <p className="eyebrow">Autonomous L1 Incident Agent</p>
            <h1>Scenario 1 operational console</h1>
          </div>
        </div>

        <div className="run-header-grid">
          <div>
            <span>Run</span>
            <code>{state.run.run_id}</code>
          </div>
          <div>
            <span>Run status</span>
            <StatusBadge value={state.run.status} tone="info" />
          </div>
          <div>
            <span>Incident</span>
            <code>{incident?.incident_id ?? "—"}</code>
          </div>
          <div>
            <span>Connection</span>
            <StatusBadge value={connection} tone={connectionTone(connection)} />
          </div>
          <div>
            <span>Last event seq</span>
            <strong>#{lastSeq}</strong>
          </div>
        </div>
      </header>

      {streamError ? (
        <div className="connection-warning" role="status">
          Persisted state remains visible while live delivery recovers.{" "}
          <span>{streamError}</span>
        </div>
      ) : null}

      <div className="console-grid">
        <section className="console-column">
          <article className="panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Current state</p>
                <h2>Incident</h2>
              </div>
              {incident ? (
                <StatusBadge
                  value={incident.status}
                  tone={incident.status === "ESCALATED" ? "warning" : "info"}
                />
              ) : null}
            </div>

            {incident ? (
              <dl className="facts-grid">
                <div>
                  <dt>Incident ID</dt>
                  <dd><code>{incident.incident_id}</code></dd>
                </div>
                <div>
                  <dt>Site</dt>
                  <dd>{incident.site_id}</dd>
                </div>
                <div>
                  <dt>Reported device</dt>
                  <dd>{incident.reported_device_id}</dd>
                </div>
                <div className="wide">
                  <dt>Symptom</dt>
                  <dd>{incident.symptom}</dd>
                </div>
              </dl>
            ) : (
              <EmptyPanel>No incident is persisted for this run.</EmptyPanel>
            )}

            {incident?.status === "ESCALATED" ? (
              <p className="semantic-note">
                Escalated means field service has been requested; it does not
                mean the device is repaired or the incident is resolved.
              </p>
            ) : null}
          </article>

          <article className="panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Observations</p>
                <h2>Evidence</h2>
              </div>
              <span className="panel-count">{state.evidence.length}</span>
            </div>

            {state.evidence.length ? (
              <div className="evidence-list">
                {state.evidence.map((evidence) => (
                  <details className="evidence-card" key={evidence.evidence_id}>
                    <summary>
                      <div>
                        <strong>{evidence.source_type}</strong>
                        <span>{formatTimestamp(evidence.captured_at)}</span>
                      </div>
                      <span className="disclosure">View</span>
                    </summary>
                    <div className="evidence-body">
                      <div className="chip-row">
                        {evidence.entity_ids.map((id) => (
                          <code key={id}>{id}</code>
                        ))}
                      </div>
                      {evidence.facts.length ? (
                        <ul className="facts-list">
                          {evidence.facts.map((fact) => (
                            <li key={fact}>{fact}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted-copy">
                          No normalized facts were persisted for this evidence.
                        </p>
                      )}
                      {evidence.expires_at ? (
                        <p className="expiry">
                          Validity timestamp:{" "}
                          <strong>{formatTimestamp(evidence.expires_at)}</strong>
                        </p>
                      ) : null}
                      <span className="subtle-label payload-label">
                        Typed safe payload
                      </span>
                      <pre className="payload-block">
                        {JSON.stringify(evidence.payload, null, 2)}
                      </pre>
                    </div>
                  </details>
                ))}
              </div>
            ) : (
              <EmptyPanel>
                No evidence has been persisted yet. Phase 6 will add live agent
                tool activity.
              </EmptyPanel>
            )}
          </article>
        </section>

        <section className="console-column timeline-column">
          <article className="panel timeline-panel">
            <div className="panel-heading sticky-heading">
              <div>
                <p className="panel-kicker">Persisted audit trail</p>
                <h2>Timeline</h2>
              </div>
              <span className="panel-count">{events.length}</span>
            </div>

            {events.length ? (
              <ol className="timeline-list">
                {events.map((event) => (
                  <li className="timeline-item" key={event.seq}>
                    <div className="timeline-rail"><span>{event.seq}</span></div>
                    <div className="timeline-content">
                      <div className="timeline-title">
                        <strong>{eventSummary(event)}</strong>
                        <time dateTime={event.occurred_at}>
                          {formatTimestamp(event.occurred_at)}
                        </time>
                      </div>
                      <code className="event-type">{event.event_type}</code>
                      <details className="event-details">
                        <summary>Safe persisted details</summary>
                        <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                      </details>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <EmptyPanel>No persisted application events were returned.</EmptyPanel>
            )}
          </article>
        </section>

        <section className="console-column">
          <article className="panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Human boundary</p>
                <h2>Proposal & approval</h2>
              </div>
              {latestProposal ? (
                <StatusBadge
                  value={latestProposal.status}
                  tone={proposalTone(latestProposal.status)}
                />
              ) : null}
            </div>

            {latestProposal ? (
              <div className="proposal-card">
                <dl className="facts-grid">
                  <div className="wide">
                    <dt>Proposal ID</dt>
                    <dd><code>{latestProposal.proposal_id}</code></dd>
                  </div>
                  <div>
                    <dt>Diagnosis</dt>
                    <dd>{latestProposal.diagnosis}</dd>
                  </div>
                  <div>
                    <dt>Action</dt>
                    <dd>{latestProposal.action_type}</dd>
                  </div>
                </dl>

                <div className="proposal-rationale">
                  <span>Rationale</span>
                  <p>{latestProposal.rationale}</p>
                </div>

                <div className="proposal-evidence">
                  <span className="subtle-label">Evidence IDs</span>
                  <div className="chip-row">
                    {latestProposal.evidence_ids.map((id) => (
                      <code key={id}>{id}</code>
                    ))}
                  </div>
                </div>

                {latestProposal.status === "PENDING_APPROVAL" ? (
                  <div className="decision-area">
                    <p>
                      Human confirmation is required before any field-service
                      action can be registered.
                    </p>
                    <div className="decision-buttons">
                      <button
                        className="approve-button"
                        type="button"
                        disabled={decision !== null}
                        onClick={() =>
                          void handleDecision(latestProposal, "approve")
                        }
                      >
                        {decision?.verb === "approve" ? "Approving…" : "Approve"}
                      </button>
                      <button
                        className="reject-button"
                        type="button"
                        disabled={decision !== null}
                        onClick={() =>
                          void handleDecision(latestProposal, "reject")
                        }
                      >
                        {decision?.verb === "reject" ? "Rejecting…" : "Reject"}
                      </button>
                    </div>
                  </div>
                ) : null}

                {latestProposal.status === "STALE" ? (
                  <p className="semantic-note stale-note">
                    Approval was recorded, but fresh authoritative conditions
                    no longer allowed execution. No field-service action was
                    created.
                  </p>
                ) : null}

                {decisionNotice ? (
                  <p className="decision-notice" role="status">
                    {decisionNotice}
                  </p>
                ) : null}

                {decisionError ? (
                  <p className="inline-error decision-error" role="alert">
                    {decisionError}
                  </p>
                ) : null}
              </div>
            ) : (
              <EmptyPanel>
                No proposal exists. This is expected before the live Phase 6
                agent creates an evidence-backed proposal.
              </EmptyPanel>
            )}
          </article>

          <article className="panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Registered outcome</p>
                <h2>Field service</h2>
              </div>
              <span className="panel-count">{state.work_orders.length}</span>
            </div>

            {state.work_orders.length ? (
              <div className="work-order-list">
                {state.work_orders.map((order) => {
                  const action = state.executed_actions.find(
                    (item) => item.proposal_id === order.proposal_id,
                  );
                  return (
                    <div className="work-order-card" key={order.work_order_id}>
                      <div className="work-order-heading">
                        <StatusBadge value="REGISTERED" tone="executed" />
                        <code>{order.work_order_id}</code>
                      </div>
                      <dl className="facts-grid">
                        <div className="wide">
                          <dt>Action ID</dt>
                          <dd><code>{action?.action_id ?? "—"}</code></dd>
                        </div>
                        <div>
                          <dt>Action type</dt>
                          <dd>{action?.action_type ?? "Field service"}</dd>
                        </div>
                        <div>
                          <dt>Device</dt>
                          <dd>{order.device_id}</dd>
                        </div>
                        <div>
                          <dt>Site</dt>
                          <dd>{order.site_id}</dd>
                        </div>
                        <div>
                          <dt>Switch / port</dt>
                          <dd>{order.switch_id} · {order.port_id}</dd>
                        </div>
                        <div>
                          <dt>Executed</dt>
                          <dd>
                            {action?.executed_at
                              ? formatTimestamp(action.executed_at)
                              : "—"}
                          </dd>
                        </div>
                        <div className="wide">
                          <dt>Work order created</dt>
                          <dd>{formatTimestamp(order.created_at)}</dd>
                        </div>
                      </dl>
                      <p className="semantic-note">
                        {FIELD_SERVICE_OUTCOME_NOTE}
                      </p>
                    </div>
                  );
                })}
              </div>
            ) : (
              <EmptyPanel>No field-service work order has been registered.</EmptyPanel>
            )}
          </article>
        </section>
      </div>

      <footer className="console-footer">
        <span>Persistent state: PostgreSQL</span>
        <span>Live transport: persisted SSE</span>
        <span>AI agent wiring: Phase 6</span>
      </footer>
    </main>
  );
}
