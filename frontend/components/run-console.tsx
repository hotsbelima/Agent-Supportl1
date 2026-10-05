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
  STALE_PROPOSAL_NOTE,
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
  const [selectedIncidentId, setSelectedIncidentId] = useState<{
    runId: string;
    id: string;
  } | null>(null);
  const [selectedObservationId, setSelectedObservationId] = useState<{
    runId: string;
    id: string;
  } | null>(null);

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
          setConnection("Reconnecting");
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
            setConnection("Reconnecting");
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

  const primaryIncident = state?.incidents[0] ?? null;
  const selectedIncidentKey =
    selectedIncidentId?.runId === runId ? selectedIncidentId.id : null;
  const selectedObservationKey =
    selectedObservationId?.runId === runId ? selectedObservationId.id : null;
  const selectedIncident = selectedIncidentKey
    ? state?.incidents.find((item) => item.incident_id === selectedIncidentKey) ?? null
    : null;
  const selectedObservation = selectedObservationKey
    ? state?.evidence.find((item) => item.evidence_id === selectedObservationKey) ?? null
    : null;
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
            <code>{primaryIncident?.incident_id ?? "—"}</code>
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
          <article className="panel scroll-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Current state</p>
                <h2>Incidents</h2>
              </div>
              {selectedIncident ? (
                <StatusBadge
                  value={selectedIncident.status}
                  tone={
                    selectedIncident.status === "ESCALATED"
                      ? "warning"
                      : "info"
                  }
                />
              ) : (
                <span className="panel-count">{state.incidents.length}</span>
              )}
            </div>

            {selectedIncident ? (
              <div className="entity-detail">
                <button
                  className="back-list-button"
                  type="button"
                  onClick={() => setSelectedIncidentId(null)}
                >
                  ← Назад к списку
                </button>
                <dl className="facts-grid">
                  <div>
                    <dt>Incident ID</dt>
                    <dd><code>{selectedIncident.incident_id}</code></dd>
                  </div>
                  <div>
                    <dt>Site</dt>
                    <dd>{selectedIncident.site_id}</dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>{selectedIncident.status}</dd>
                  </div>
                  <div>
                    <dt>Reported device</dt>
                    <dd>{selectedIncident.reported_device_id}</dd>
                  </div>
                  <div className="wide">
                    <dt>Summary</dt>
                    <dd>{selectedIncident.symptom}</dd>
                  </div>
                  <div className="wide">
                    <dt>Updated</dt>
                    <dd>{formatTimestamp(selectedIncident.updated_at)}</dd>
                  </div>
                </dl>
                {selectedIncident.status === "ESCALATED" ? (
                  <p className="semantic-note">
                    Escalated means field service has been requested; it does not
                    mean the device is repaired or the incident is resolved.
                  </p>
                ) : null}
              </div>
            ) : state.incidents.length ? (
              <div className="entity-list" role="list">
                {state.incidents.map((item) => (
                  <div className="entity-row" role="listitem" key={item.incident_id}>
                    <div className="entity-row-main">
                      <strong>{item.symptom}</strong>
                      <span>{item.site_id}</span>
                    </div>
                    <StatusBadge
                      value={item.status}
                      tone={item.status === "ESCALATED" ? "warning" : "info"}
                    />
                    <button
                      className="detail-button"
                      type="button"
                      onClick={() => setSelectedIncidentId({ runId, id: item.incident_id })}
                    >
                      Подробнее
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyPanel>No incident is persisted for this run.</EmptyPanel>
            )}
          </article>

          <article className="panel scroll-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Safe Product evidence</p>
                <h2>Observations</h2>
              </div>
              <span className="panel-count">{state.evidence.length}</span>
            </div>

            {selectedObservation ? (
              <div className="entity-detail">
                <button
                  className="back-list-button"
                  type="button"
                  onClick={() => setSelectedObservationId(null)}
                >
                  ← Назад к списку
                </button>
                <dl className="facts-grid">
                  <div>
                    <dt>Type</dt>
                    <dd>{selectedObservation.source_type}</dd>
                  </div>
                  <div>
                    <dt>Captured</dt>
                    <dd>{formatTimestamp(selectedObservation.captured_at)}</dd>
                  </div>
                  <div className="wide">
                    <dt>Evidence ID</dt>
                    <dd><code>{selectedObservation.evidence_id}</code></dd>
                  </div>
                  <div className="wide">
                    <dt>Source / entity context</dt>
                    <dd>
                      {selectedObservation.entity_ids.length
                        ? selectedObservation.entity_ids.join(" · ")
                        : "—"}
                    </dd>
                  </div>
                </dl>
                {selectedObservation.facts.length ? (
                  <ul className="facts-list observation-facts">
                    {selectedObservation.facts.map((fact) => (
                      <li key={fact}>{fact}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted-copy observation-copy">
                    No normalized facts were persisted for this observation.
                  </p>
                )}
                {selectedObservation.expires_at ? (
                  <p className="expiry observation-copy">
                    Validity timestamp:{" "}
                    <strong>
                      {formatTimestamp(selectedObservation.expires_at)}
                    </strong>
                  </p>
                ) : null}
                <div className="observation-payload">
                  <span className="subtle-label payload-label">
                    Typed safe payload
                  </span>
                  <pre className="payload-block">
                    {JSON.stringify(selectedObservation.payload, null, 2)}
                  </pre>
                </div>
              </div>
            ) : state.evidence.length ? (
              <div className="entity-list" role="list">
                {state.evidence.map((evidence) => (
                  <div
                    className="entity-row observation-row"
                    role="listitem"
                    key={evidence.evidence_id}
                  >
                    <div className="entity-row-main">
                      <strong>{evidence.source_type}</strong>
                      <span>
                        {evidence.entity_ids[0] ?? "Product observation"}
                      </span>
                      <time dateTime={evidence.captured_at}>
                        {formatTimestamp(evidence.captured_at)}
                      </time>
                    </div>
                    <button
                      className="detail-button"
                      type="button"
                      onClick={() =>
                        setSelectedObservationId({
                          runId,
                          id: evidence.evidence_id,
                        })
                      }
                    >
                      Подробнее
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyPanel>
                No observations have been persisted yet. The event-driven agent
                will add safe typed evidence as it investigates.
              </EmptyPanel>
            )}
          </article>
        </section>

        <section className="console-column timeline-column">
          <article className="panel scroll-panel timeline-panel">
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
          <article className="panel scroll-panel">
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
                    {STALE_PROPOSAL_NOTE}
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

          <article className="panel scroll-panel">
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
        <span>AI dispatch: persisted event → native ADK</span>
      </footer>
    </main>
  );
}
