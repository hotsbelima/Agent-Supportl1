"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  decideProposal,
  displayApiError,
  getЗапускState,
  getЗапускХронология,
  isRetryableApiFailure,
} from "@/lib/api";
import {
  abortableDelay,
  applyХронологияEvent,
  bootstrapPersistedЗапуск,
  connectionStateForFailure,
  decisionRecoveryСтатус,
  emptyХронология,
  isStateRefreshEvent,
  mergeХронологияEvents,
  nextTransportFailure,
  prepareReconnect,
  reconnectDelayMs,
  replayNotice,
  ХронологияGapError,
  type ХронологияAccumulator,
} from "@/lib/recovery";
import {
  connectionLabel,
  connectionTone,
  eventОписание,
  FIELD_SERVICE_OUTCOME_NOTE,
  formatTimestamp,
  observationState,
  proposalTone,
  statusLabel,
  STALE_PROPOSAL_NOTE,
} from "@/lib/presentation";
import { streamЗапускEvents } from "@/lib/sse";
import type {
  ApplicationEventView,
  СоединениеState,
  ProposalView,
  ЗапускStateResponse,
} from "@/lib/types";

const DEMO_OPERATOR = "portfolio-demo-operator";

function СтатусBadge({
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
  if (error instanceof ХронологияGapError) {
    return "Обнаружен пропуск в хронологии; восстанавливаем сохранённые события.";
  }
  if (error instanceof Error && error.message === "Live event stream closed.") {
    return "Live-лента закрылась; переподключаемся из сохранённого состояния.";
  }
  return displayApiError(error);
}

export function ЗапускConsole({ runId }: { runId: string }) {
  const [state, setState] = useState<ЗапускStateResponse | null>(null);
  const [events, setEvents] = useState<ApplicationEventView[]>([]);
  const [connection, setСоединение] =
    useState<СоединениеState>("Reconnecting");
  const [loading, setLoading] = useState(true);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [decision, setDecision] = useState<{
    proposalId: string;
    verb: "approve" | "reject";
  } | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [decisionNotice, setDecisionNotice] = useState<string | null>(null);
  const [selectedИнцидентId, setSelectedИнцидентId] = useState<{
    runId: string;
    id: string;
  } | null>(null);
  const [selectedObservationId, setSelectedObservationId] = useState<{
    runId: string;
    id: string;
  } | null>(null);

  const timelineByЗапускRef = useRef(new Map<string, ХронологияAccumulator>());
  const cursorByЗапускRef = useRef(new Map<string, number>());
  const stateSeqByЗапускRef = useRef(new Map<string, number>());

  const publishState = useCallback(
    (current: ЗапускStateResponse) => {
      const previousSeq = stateSeqByЗапускRef.current.get(runId) ?? -1;
      if (current.latest_event_seq >= previousSeq) {
        stateSeqByЗапускRef.current.set(runId, current.latest_event_seq);
        setState(current);
      }
      return current;
    },
    [runId],
  );

  const refreshState = useCallback(
    async (signal?: AbortSignal) => {
      const current = await getЗапускState(runId, signal);
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
      requestedЗапускId: string,
      signal?: AbortSignal,
    ) => getЗапускState(requestedЗапускId, signal);
    const readPage = (
      requestedЗапускId: string,
      afterSeq: number,
      limit: number,
      signal?: AbortSignal,
    ) => getЗапускХронология(requestedЗапускId, afterSeq, limit, signal);

    function currentХронология(): ХронологияAccumulator {
      return timelineByЗапускRef.current.get(runId) ?? emptyХронология(
        cursorByЗапускRef.current.get(runId) ?? 0,
      );
    }

    function publishХронология(next: ХронологияAccumulator) {
      timelineByЗапускRef.current.set(runId, next);
      cursorByЗапускRef.current.set(runId, next.cursor);
      if (mounted) setEvents(next.events);
    }

    async function runSession() {
      setLoading(true);
      setPageError(null);
      setStreamError(null);
      setСоединение("Reconnecting");
      setDecisionError(null);
      setDecisionNotice(null);

      timelineByЗапускRef.current.set(runId, emptyХронология());
      cursorByЗапускRef.current.set(runId, 0);
      stateSeqByЗапускRef.current.set(runId, -1);

      while (!controller.signal.aborted) {
        try {
          const bootstrapped = await bootstrapPersistedЗапуск({
            runId,
            readState,
            readPage,
            signal: controller.signal,
          });
          if (!mounted) return;

          publishState(bootstrapped.state);
          publishХронология(bootstrapped.timeline);
          failureCount = 0;
          setСоединение("Reconnecting");
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
            setСоединение("Offline/Unavailable");
            setPageError(displayApiError(error));
            return;
          }

          const failure = nextTransportFailure(failureCount);
          failureCount = failure.failureCount;
          setСоединение(failure.connection);
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
            setСоединение(connectionStateForFailure(failureCount));
            await abortableDelay(
              reconnectDelayMs(failureCount),
              controller.signal,
            );

            const cursor = cursorByЗапускRef.current.get(runId) ?? 0;
            const recovered = await prepareReconnect({
              runId,
              cursor,
              readState,
              readPage,
              signal: controller.signal,
            });
            if (!mounted) return;

            const merged = mergeХронологияEvents(
              currentХронология(),
              recovered.backfill.events,
              runId,
            );
            publishState(recovered.state);
            publishХронология(merged);
            setСоединение("Reconnecting");
          }

          const cursor = cursorByЗапускRef.current.get(runId) ?? 0;
          await streamЗапускEvents({
            runId,
            afterSeq: cursor,
            lastEventId: needsRecovery ? cursor : undefined,
            signal: controller.signal,
            onOpen: () => {
              if (!mounted) return;
              setСоединение("Live");
              setStreamError(null);
            },
            onHeartbeat: () => {
              failureCount = 0;
            },
            onEvent: (event) => {
              if (!mounted) return;

              const result = applyХронологияEvent(
                currentХронология(),
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
              publishХронология(result.timeline);

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
          setСоединение(failure.connection);
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

  const primaryИнцидент = state?.incidents[0] ?? null;
  const selectedИнцидентKey =
    selectedИнцидентId?.runId === runId ? selectedИнцидентId.id : null;
  const selectedObservationKey =
    selectedObservationId?.runId === runId ? selectedObservationId.id : null;
  const selectedИнцидент = selectedИнцидентKey
    ? state?.incidents.find((item) => item.incident_id === selectedИнцидентKey) ?? null
    : null;
  const selectedObservation = selectedObservationKey
    ? state?.evidence.find((item) => item.evidence_id === selectedObservationKey) ?? null
    : null;
  const lastSeq = events.at(-1)?.seq ?? 0;
  const scenarioLabel =
    state?.run.scenario_id === "scenario-3"
      ? "Сценарий 3"
      : state?.run.scenario_id === "scenario-1"
        ? "Сценарий 1"
        : state?.run.scenario_id ?? "Неизвестный сценарий";

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
          "Решение сохранено, но полное состояние временно недоступно. После переподключения интерфейс синхронизируется с Product state.",
        );
      }
    } catch (error) {
      try {
        const recovered = await refreshState();
        const recovery = decisionRecoveryСтатус(
          recovered,
          proposal.proposal_id,
        );

        if (recovery === "persisted") {
          setDecisionNotice(
            "Ответ на решение прервался; сохранённое Product state успешно восстановлено.",
          );
          setDecisionError(null);
        } else if (recovery === "still-pending") {
          setDecisionError(
            `${displayApiError(error)} Product state всё ещё показывает ожидание решения; повтор того же решения безопасен.`,
          );
        } else if (recovery === "inconsistent") {
          setDecisionError(
            "Ответ прервался, а сохранённое состояние выглядит несогласованным; выполнение не показывается как подтверждённое.",
          );
        } else {
          setDecisionError(
            "Ответ прервался, и предложение не удалось подтвердить по авторитетному Product state.",
          );
        }
      } catch {
        setDecisionError(
          "Результат решения не подтверждён. Переподключение восстановит Product state; повтор решения остаётся идемпотентным.",
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
          <p>{pageError ?? "Product API не вернул состояние запуска."}</p>
          <Link className="secondary-button" href="/">
            К выбору сценариев
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
            <p className="eyebrow">Автономный L1 Инцидент Agent</p>
            <h1>{scenarioLabel} · операционная консоль</h1>
          </div>
        </div>

        <div className="run-header-actions">
          <Link className="secondary-button compact-button" href="/">
            Новый запуск
          </Link>
        </div>

        <div className="run-header-grid">
          <div>
            <span>Запуск</span>
            <code>{state.run.run_id}</code>
          </div>
          <div>
            <span>Сценарий</span>
            <strong>{state.run.scenario_id}</strong>
          </div>
          <div>
            <span>Статус запуска</span>
            <СтатусBadge value={state.run.status} tone="info" />
          </div>
          <div>
            <span>Инцидент</span>
            <code>{primaryИнцидент?.incident_id ?? "—"}</code>
          </div>
          <div>
            <span>Соединение</span>
            <СтатусBadge value={connection} tone={connectionTone(connection)} />
          </div>
          <div>
            <span>Последнее событие</span>
            <strong>#{lastSeq}</strong>
          </div>
        </div>
      </header>

      {streamError ? (
        <div className="connection-warning" role="status">
          Сохранённое состояние остаётся доступным, пока live-доставка восстанавливается.{" "}
          <span>{streamError}</span>
        </div>
      ) : null}

      <div className="console-grid">
        <section className="console-column">
          <article className="panel scroll-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Текущее состояние</p>
                <h2>Инцидентs</h2>
              </div>
              {selectedИнцидент ? (
                <СтатусBadge
                  value={selectedИнцидент.status}
                  tone={
                    selectedИнцидент.status === "ESCALATED"
                      ? "warning"
                      : "info"
                  }
                />
              ) : (
                <span className="panel-count">{state.incidents.length}</span>
              )}
            </div>

            {selectedИнцидент ? (
              <div className="entity-detail">
                <button
                  className="back-list-button"
                  type="button"
                  onClick={() => setSelectedИнцидентId(null)}
                >
                  ← Назад к списку
                </button>
                <dl className="facts-grid">
                  <div>
                    <dt>Инцидент ID</dt>
                    <dd><code>{selectedИнцидент.incident_id}</code></dd>
                  </div>
                  <div>
                    <dt>Площадка</dt>
                    <dd>{selectedИнцидент.site_id}</dd>
                  </div>
                  <div>
                    <dt>Статус</dt>
                    <dd>{selectedИнцидент.status}</dd>
                  </div>
                  <div>
                    <dt>Устройство</dt>
                    <dd>{selectedИнцидент.reported_device_id}</dd>
                  </div>
                  <div className="wide">
                    <dt>Описание</dt>
                    <dd>{selectedИнцидент.symptom}</dd>
                  </div>
                  <div className="wide">
                    <dt>Обновлён</dt>
                    <dd>{formatTimestamp(selectedИнцидент.updated_at)}</dd>
                  </div>
                </dl>
                {selectedИнцидент.status === "ESCALATED" ? (
                  <p className="semantic-note">
                    Эскалация означает, что выезд Field Service запрошен; это не означает, что устройство уже отремонтировано или инцидент закрыт.
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
                    <СтатусBadge
                      value={statusLabel(item.status)}
                      tone={item.status === "ESCALATED" ? "warning" : "info"}
                    />
                    <button
                      className="detail-button"
                      type="button"
                      onClick={() => setSelectedИнцидентId({ runId, id: item.incident_id })}
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

          <article className="panel scroll-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Безопасные факты Product</p>
                <h2>Наблюдения</h2>
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
                    <dt>Тип</dt>
                    <dd>{selectedObservation.source_type}</dd>
                  </div>
                  <div>
                    <dt>Получено</dt>
                    <dd>{formatTimestamp(selectedObservation.captured_at)}</dd>
                  </div>
                  <div className="wide">
                    <dt>Evidence ID</dt>
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
                      <li key={fact}>{fact}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted-copy observation-copy">
                    Для этого наблюдения пока нет нормализованных фактов.
                  </p>
                )}
                {selectedObservation.expires_at ? (
                  <p className="expiry observation-copy">
                    Действительно до:{" "}
                    <strong>
                      {formatTimestamp(selectedObservation.expires_at)}
                    </strong>
                  </p>
                ) : null}
                <div className="observation-payload">
                  <span className="subtle-label payload-label">
                    Типd safe payload
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
                        {evidence.entity_ids[0] ?? "Product Evidence"}
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
                Наблюдений пока нет. Event-driven агент добавит безопасные Evidence по мере расследования.
              </EmptyPanel>
            )}
          </article>
        </section>

        <section className="console-column timeline-column">
          <article className="panel scroll-panel timeline-panel">
            <div className="panel-heading sticky-heading">
              <div>
                <p className="panel-kicker">Сохранённый audit trail</p>
                <h2>Хронология</h2>
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
                        <strong>{eventОписание(event)}</strong>
                        <time dateTime={event.occurred_at}>
                          {formatTimestamp(event.occurred_at)}
                        </time>
                      </div>
                      <code className="event-type">{event.event_type}</code>
                      <details className="event-details">
                        <summary>Безопасные сохранённые детали</summary>
                        <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                      </details>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <EmptyPanel>Сохранённых application events пока нет.</EmptyPanel>
            )}
          </article>
        </section>

        <section className="console-column">
          <article className="panel scroll-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Граница человеческого решения</p>
                <h2>Предложение и решение</h2>
              </div>
              {latestProposal ? (
                <СтатусBadge
                  value={latestProposal.status}
                  tone={proposalTone(latestProposal.status)}
                />
              ) : null}
            </div>

            {latestProposal ? (
              <div className="proposal-card">
                <dl className="facts-grid">
                  <div className="wide">
                    <dt>ID предложения</dt>
                    <dd><code>{latestProposal.proposal_id}</code></dd>
                  </div>
                  <div>
                    <dt>Диагноз</dt>
                    <dd>{latestProposal.diagnosis}</dd>
                  </div>
                  <div>
                    <dt>Действие</dt>
                    <dd>{latestProposal.action_type}</dd>
                  </div>
                </dl>

                <div className="proposal-rationale">
                  <span>Обоснование</span>
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
                      До регистрации действия Field Service требуется решение человека.
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
                Предложения пока нет. Агент создаст его только после достаточного набора сохранённых Evidence.
              </EmptyPanel>
            )}
          </article>

          <article className="panel scroll-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Зарегистрированный результат</p>
                <h2>Field Service</h2>
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
                        <СтатусBadge value="REGISTERED" tone="executed" />
                        <code>{order.work_order_id}</code>
                      </div>
                      <dl className="facts-grid">
                        <div className="wide">
                          <dt>Действие ID</dt>
                          <dd><code>{action?.action_id ?? "—"}</code></dd>
                        </div>
                        <div>
                          <dt>Действие type</dt>
                          <dd>{action?.action_type ?? "Field Service"}</dd>
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
                          <dt>Work Order создан</dt>
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
              <EmptyPanel>Work Order Field Service ещё не зарегистрирован.</EmptyPanel>
            )}
          </article>
        </section>
      </div>

      <footer className="console-footer">
        <span>Источник истины: PostgreSQL Product state</span>
        <span>Live transport: persisted SSE</span>
        <span>AI dispatch: persisted event → native ADK</span>
      </footer>
    </main>
  );
}
