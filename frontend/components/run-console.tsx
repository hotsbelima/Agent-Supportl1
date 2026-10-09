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
  actionTypeLabel,
  activityKindLabel,
  connectionLabel,
  connectionTone,
  diagnosisLabel,
  eventSummary,
  eventTypeLabel,
  evidenceEntityLabel,
  evidenceSourceLabel,
  FIELD_SERVICE_OUTCOME_NOTE,
  formatTimestamp,
  incidentTextLabel,
  observationState,
  nativeHitlReady,
  playbackIncidentStatus,
  playbackVisibility,
  proposalRationale,
  proposalTone,
  shouldRevealProposalPanel,
  statusLabel,
  STALE_PROPOSAL_NOTE,
  standardInvestigationActivities,
  userFacingTextLabel,
  visibleTimelineEvents,
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
      {statusLabel(value)}
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
    return "Обнаружен пропуск в хронологии; восстанавливаем сохранённые события.";
  }
  if (error instanceof Error && error.message === "Live event stream closed.") {
    return "Поток событий прервался; переподключаемся из сохранённого состояния.";
  }
  return displayApiError(error);
}

export function RunConsole({ runId }: { runId: string }) {
  const [state, setState] = useState<RunStateResponse | null>(null);
  const [events, setEvents] = useState<ApplicationEventView[]>([]);
  const [playbackNow, setPlaybackNow] = useState(() => Date.now());
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
  const [journalState, setJournalState] = useState({
    runId,
    visible: false,
  });
  const journalVisible =
    journalState.runId === runId ? journalState.visible : false;
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
            `${displayApiError(error)} Повторно загружаем сохранённое состояние…`,
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

  useEffect(() => {
    const timerId = window.setInterval(() => {
      setPlaybackNow(Date.now());
    }, 1_000);

    return () => window.clearInterval(timerId);
  }, [runId]);

  const visibleEvents = state
    ? visibleTimelineEvents(events, state.run.created_at, playbackNow)
    : [];
  const investigationActivities = state
    ? standardInvestigationActivities(visibleEvents, state)
    : [];
  const playback = playbackVisibility(visibleEvents);
  const visibleEvidence = state
    ? state.evidence.filter((item) => playback.evidenceIds.has(item.evidence_id))
    : [];
  const visibleProposals = state?.proposals ?? [];
  const visibleWorkOrders = state?.work_orders ?? [];
  const visibleExecutedActions = state?.executed_actions ?? [];
  const actionExecuted = visibleExecutedActions.length > 0;

  const selectedIncidentKey =
    selectedIncidentId?.runId === runId ? selectedIncidentId.id : null;
  const selectedObservationKey =
    selectedObservationId?.runId === runId ? selectedObservationId.id : null;
  const selectedIncident = selectedIncidentKey
    ? state?.incidents.find((item) => item.incident_id === selectedIncidentKey) ?? null
    : null;
  const selectedObservation = selectedObservationKey
    ? visibleEvidence.find((item) => item.evidence_id === selectedObservationKey) ?? null
    : null;
  const scenarioLabel =
    state?.run.scenario_id === "scenario-3"
      ? "Сценарий 3"
      : state?.run.scenario_id === "scenario-1"
        ? "Сценарий 1"
        : state?.run.scenario_id ?? "Неизвестный сценарий";

  const latestProposal: ProposalView | null = visibleProposals.length
    ? [...visibleProposals]
        .sort((a, b) => a.created_at.localeCompare(b.created_at))
        .at(-1) ?? null
    : null;
  const showProposalPanel = shouldRevealProposalPanel(
    state?.run.scenario_id,
    latestProposal?.proposal_id ?? null,
    playback.proposalIds,
  );
  const latestProposalDisplayStatus = latestProposal?.status ?? null;
  const latestProposalHitlReady =
    latestProposal !== null &&
    nativeHitlReady(events, latestProposal.proposal_id);

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
          "Решение сохранено, но полное состояние временно недоступно. После переподключения интерфейс синхронизируется с состоянием продукта.",
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
            "Ответ на решение прервался; сохранённое состояние продукта успешно восстановлено.",
          );
          setDecisionError(null);
        } else if (recovery === "still-pending") {
          setDecisionError(
            `${displayApiError(error)} Состояние продукта всё ещё ожидает решения; повтор безопасен.`,
          );
        } else if (recovery === "inconsistent") {
          setDecisionError(
            "Ответ прервался, а сохранённое состояние выглядит несогласованным; выполнение не показывается как подтверждённое.",
          );
        } else {
          setDecisionError(
            "Ответ прервался, и предложение не удалось подтвердить по авторитетному состоянию продукта.",
          );
        }
      } catch {
        setDecisionError(
          "Результат решения не подтверждён. Переподключение восстановит состояние продукта; повтор решения остаётся идемпотентным.",
        );
      }
    } finally {
      setDecision(null);
    }
  }

  if (loading) {
    return (
      <main className="console-shell">
        <div className="console-loading" role="status" aria-live="polite">
          <span className="spinner" aria-hidden="true" />
          <strong>Загружаем сохранённый запуск</strong>
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
          <p className="eyebrow">Запуск недоступен</p>
          <h1>Не удалось загрузить операционное состояние</h1>
          <p>{pageError ?? "API продукта не вернул состояние запуска."}</p>
          <Link className="secondary-button" href="/">
            К выбору сценариев
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="console-shell">
      {streamError ? (
        <div className="connection-warning" role="status">
          Сохранённое состояние остаётся доступным, пока поток событий восстанавливается.{" "}
          <span>{streamError}</span>
        </div>
      ) : null}

      <div className="console-grid">
        <section className="console-column">
          <article className="panel scroll-panel incident-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Текущее состояние</p>
                <h2>Инциденты</h2>
              </div>
              {selectedIncident ? (
                <StatusBadge
                  value={playbackIncidentStatus(
                    selectedIncident.status,
                    actionExecuted,
                  )}
                  tone={
                    playbackIncidentStatus(
                      selectedIncident.status,
                      actionExecuted,
                    ) === "ESCALATED"
                      ? "warning"
                      : "info"
                  }
                />
              ) : null}
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
                    <dt>ID инцидента</dt>
                    <dd><code>{selectedIncident.incident_id}</code></dd>
                  </div>
                  <div>
                    <dt>Площадка</dt>
                    <dd>{selectedIncident.site_id}</dd>
                  </div>
                  <div>
                    <dt>Статус</dt>
                    <dd>
                      {statusLabel(
                        playbackIncidentStatus(
                          selectedIncident.status,
                          actionExecuted,
                        ),
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>Устройство</dt>
                    <dd>{selectedIncident.reported_device_id}</dd>
                  </div>
                  <div className="wide">
                    <dt>Описание</dt>
                    <dd>{incidentTextLabel(selectedIncident.symptom)}</dd>
                  </div>
                  <div className="wide">
                    <dt>Обновлён</dt>
                    <dd>{formatTimestamp(selectedIncident.updated_at)}</dd>
                  </div>
                </dl>
                {playbackIncidentStatus(
                  selectedIncident.status,
                  actionExecuted,
                ) === "ESCALATED" ? (
                  <p className="semantic-note">
                    Эскалация означает, что выездной сервис запрошен; это не означает, что устройство уже отремонтировано или инцидент закрыт.
                  </p>
                ) : null}
              </div>
            ) : state.incidents.length ? (
              <div className="entity-list" role="list">
                {state.incidents.map((item) => (
                  <div className="entity-row" role="listitem" key={item.incident_id}>
                    <div className="entity-row-main">
                      <strong>{incidentTextLabel(item.symptom)}</strong>
                      <span>{item.site_id}</span>
                    </div>
                    <StatusBadge
                      value={playbackIncidentStatus(
                        item.status,
                        actionExecuted,
                      )}
                      tone={
                        playbackIncidentStatus(
                          item.status,
                          actionExecuted,
                        ) === "ESCALATED"
                          ? "warning"
                          : "info"
                      }
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
              <EmptyPanel>Для этого запуска пока не сохранено ни одного инцидента.</EmptyPanel>
            )}
          </article>

          <article className="panel scroll-panel observation-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Наблюдаемые факты</p>
                <h2>Наблюдения</h2>
              </div>
              
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
                    <dt>Тип</dt>
                    <dd>{evidenceSourceLabel(selectedObservation.source_type)}</dd>
                  </div>
                  <div>
                    <dt>Получено</dt>
                    <dd>{formatTimestamp(selectedObservation.captured_at)}</dd>
                  </div>
                  <div className="wide">
                    <dt>ID наблюдения</dt>
                    <dd><code>{selectedObservation.evidence_id}</code></dd>
                  </div>
                  <div className="wide">
                    <dt>Связанные сущности</dt>
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
                      <li key={fact}>{userFacingTextLabel(fact)}</li>
                    ))}
                  </ul>
                ) : null}
                <div className="observation-payload">
                  <span className="subtle-label payload-label">
                    Данные
                  </span>
                  <pre className="payload-block">
                    {JSON.stringify(selectedObservation.payload, null, 2)}
                  </pre>
                </div>
              </div>
            ) : visibleEvidence.length ? (
              <div className="entity-list" role="list">
                {visibleEvidence.map((evidence) => (
                  <div
                    className="entity-row observation-row"
                    role="listitem"
                    key={evidence.evidence_id}
                  >
                    <div className="entity-row-main">
                      <strong>{evidenceSourceLabel(evidence.source_type)}</strong>
                      <span>
                        {evidenceEntityLabel(evidence)}
                      </span>
                      <time dateTime={evidence.captured_at}>
                        {formatTimestamp(evidence.captured_at)}
                      </time>
                      {observationState(evidence) ? (
                        <span className="observation-state">
                          Состояние: {statusLabel(observationState(evidence)!)}
                        </span>
                      ) : null}
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
                Наблюдений пока нет. Событийный агент добавит безопасные факты по мере расследования.
              </EmptyPanel>
            )}
          </article>
        </section>

        <section className="console-column timeline-column">
          <article className="panel scroll-panel investigation-panel">
            <div className="panel-heading sticky-heading">
              <div>
                <p className="panel-kicker">
                  Что происходило и к каким выводам пришёл агент
                </p>
                <h2>Ход расследования</h2>
              </div>
              
            </div>

            {investigationActivities.length ? (
              <ol className="activity-list">
                {investigationActivities.map((item) => (
                  <li className="activity-item" data-kind={item.kind} key={item.id}>
                    <div className="activity-meta">
                      <span>{activityKindLabel(item.kind)}</span>
                      <time dateTime={item.occurred_at}>
                        {formatTimestamp(item.occurred_at)}
                      </time>
                    </div>
                    <strong>{item.title}</strong>
                    {item.detail ? <p>{item.detail}</p> : null}
                  </li>
                ))}
              </ol>
            ) : (
              <EmptyPanel>
                Ход расследования появится после первых подтверждённых событий.
              </EmptyPanel>
            )}
          </article>

          <article className="panel scroll-panel timeline-panel">
            <div className="panel-heading sticky-heading">
              <div>
                <p className="panel-kicker">События системы</p>
                <h2>Технический журнал</h2>
              </div>
              <button
                className="journal-toggle"
                type="button"
                onClick={() =>
                  setJournalState((current) => ({
                    runId,
                    visible:
                      current.runId === runId ? !current.visible : true,
                  }))
                }
                aria-expanded={journalVisible}
              >
                {journalVisible ? "Скрыть журнал" : "Показать журнал"}
              </button>
            </div>

            {!journalVisible ? (
              <div className="journal-hidden-copy">
                Содержимое журнала скрыто, чтобы не перегружать интерфейс технической информацией.
              </div>
            ) : visibleEvents.length ? (
              <ol className="timeline-list">
                {visibleEvents.map((event) => (
                  <li className="timeline-item" key={event.seq}>
                    <div className="timeline-rail"><span>{event.seq}</span></div>
                    <div className="timeline-content">
                      <div className="timeline-title">
                        <strong>{eventSummary(event)}</strong>
                        <time dateTime={event.occurred_at}>
                          {formatTimestamp(event.occurred_at)}
                        </time>
                      </div>
                      <span className="event-type">{eventTypeLabel(event.event_type)}</span>
                      <details className="event-details">
                        <summary>Детали</summary>
                        <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                      </details>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <EmptyPanel>Событий системы пока нет.</EmptyPanel>
            )}
          </article>
        </section>

        <section
          className={
            showProposalPanel ? "console-column" : "console-column proposal-pending"
          }
        >
          {showProposalPanel ? (
            <article className="panel scroll-panel decision-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Подтверждение действий агента</p>
                <h2>Предложение и решение</h2>
              </div>
              {latestProposal ? (
                <StatusBadge
                  value={latestProposalDisplayStatus ?? latestProposal.status}
                  tone={proposalTone(
                    latestProposalDisplayStatus ?? latestProposal.status,
                  )}
                />
              ) : null}
            </div>

            {latestProposal ? (
              <div className="proposal-card">
                {latestProposal.status === "PENDING_APPROVAL" && latestProposalHitlReady ? (
                  <div className="decision-area">
                    <p>
                      До регистрации действия выездного сервиса требуется решение человека.
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
                        {decision?.verb === "approve" ? "Одобряем…" : "Одобрить"}
                      </button>
                      <button
                        className="reject-button"
                        type="button"
                        disabled={decision !== null}
                        onClick={() =>
                          void handleDecision(latestProposal, "reject")
                        }
                      >
                        {decision?.verb === "reject" ? "Отклоняем…" : "Отклонить"}
                      </button>
                    </div>
                  </div>
                ) : null}

                <dl className="facts-grid">
                  <div className="wide">
                    <dt>ID предложения</dt>
                    <dd><code>{latestProposal.proposal_id}</code></dd>
                  </div>
                  <div>
                    <dt>Диагноз</dt>
                    <dd>{diagnosisLabel(latestProposal.diagnosis)}</dd>
                  </div>
                  <div>
                    <dt>Действие</dt>
                    <dd>{actionTypeLabel(latestProposal.action_type)}</dd>
                  </div>
                </dl>

                <div className="proposal-rationale">
                  <span>Обоснование</span>
                  <p>{proposalRationale(latestProposal)}</p>
                </div>

                <div className="proposal-evidence">
                  <span className="subtle-label">ID наблюдений</span>
                  <div className="chip-row">
                    {latestProposal.evidence_ids.map((id) => (
                      <code key={id}>{id}</code>
                    ))}
                  </div>
                </div>

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
                Предложения пока нет. Агент создаст его только после достаточного набора сохранённых наблюдений.
              </EmptyPanel>
            )}
            </article>
          ) : null}

          <article className="panel scroll-panel result-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Результат действия</p>
                <h2>Что сделано</h2>
              </div>
              
            </div>

            {visibleWorkOrders.length ? (
              <div className="work-order-list">
                {visibleWorkOrders.map((order) => {
                  const action = visibleExecutedActions.find(
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
                          <dt>ID действия</dt>
                          <dd><code>{action?.action_id ?? "—"}</code></dd>
                        </div>
                        <div>
                          <dt>Тип действия</dt>
                          <dd>{action ? actionTypeLabel(action.action_type) : "Выездной сервис"}</dd>
                        </div>
                        <div>
                          <dt>Устройство</dt>
                          <dd>{order.device_id}</dd>
                        </div>
                        <div>
                          <dt>Площадка</dt>
                          <dd>{order.site_id}</dd>
                        </div>
                        <div>
                          <dt>Коммутатор / порт</dt>
                          <dd>{order.switch_id} · {order.port_id}</dd>
                        </div>
                        <div>
                          <dt>Выполнено</dt>
                          <dd>
                            {action?.executed_at
                              ? formatTimestamp(action.executed_at)
                              : "—"}
                          </dd>
                        </div>
                        <div className="wide">
                          <dt>Заявка на выезд создана</dt>
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
            ) : null}
          </article>
        </section>
      </div>

      <footer className="run-footer-bar">
        <strong>{scenarioLabel} · операционная консоль</strong>
        <div className="run-footer-actions">
          <span className="status-badge" data-tone={connectionTone(connection)}>
            {connectionLabel(connection)}
          </span>
          <Link className="secondary-button compact-button" href="/">
            Новый запуск
          </Link>
        </div>
      </footer>
    </main>
  );
}
