"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  advanceScenario2Simulator,
  decideScenario2Proposal,
  displayApiError,
  getRunTimeline,
  getScenario2State,
  isRetryableApiFailure,
} from "@/lib/api";
import {
  connectionLabel,
  connectionTone,
  eventSummary,
  formatTimestamp,
  majorIncidentRationale,
  observationState,
  proposalTone,
  statusLabel,
  STALE_PROPOSAL_NOTE,
} from "@/lib/presentation";
import { abortableDelay } from "@/lib/recovery";
import { streamRunEvents } from "@/lib/sse";
import type {
  ApplicationEventView,
  ConnectionState,
  MajorIncidentProposalView,
  Scenario2IngestionStateResponse,
} from "@/lib/types";

const DEMO_OPERATOR = "portfolio-demo-operator";
const AUTO_SIGNAL_INTERVAL_MS = 20_000;
const CANONICAL_SIGNAL_COUNT = 3;

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

export function Scenario2Console({ runId }: { runId: string }) {
  const [state, setState] = useState<Scenario2IngestionStateResponse | null>(null);
  const [events, setEvents] = useState<ApplicationEventView[]>([]);
  const [connection, setConnection] =
    useState<ConnectionState>("Reconnecting");
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [progressNotice, setProgressNotice] = useState<string | null>(null);
  const [decision, setDecision] = useState<{
    proposalId: string;
    verb: "approve" | "reject";
  } | null>(null);
  const [decisionNotice, setDecisionNotice] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(
    null,
  );
  const [selectedObservationId, setSelectedObservationId] =
    useState<string | null>(null);

  const cursorRef = useRef(0);
  const autoAdvanceInFlightRef = useRef(false);

  const refreshState = useCallback(
    async (signal?: AbortSignal) => {
      const next = await getScenario2State(runId, signal);
      setState(next);
      return next;
    },
    [runId],
  );

  useEffect(() => {
    const controller = new AbortController();
    let mounted = true;

    async function loadInitial() {
      setLoading(true);
      setPageError(null);
      setConnection("Reconnecting");

      while (!controller.signal.aborted) {
        try {
          const [snapshot, timeline] = await Promise.all([
            getScenario2State(runId, controller.signal),
            getRunTimeline(runId, 0, 1000, controller.signal),
          ]);
          if (!mounted) return;

          setState(snapshot);
          setEvents(timeline.events);
          cursorRef.current = timeline.next_cursor;
          setLoading(false);
          setConnection("Reconnecting");
          break;
        } catch (error) {
          if (!mounted || isAbortError(error)) return;
          setPageError(displayApiError(error));

          if (!isRetryableApiFailure(error)) {
            setLoading(false);
            setConnection("Offline/Unavailable");
            return;
          }

          try {
            await abortableDelay(1200, controller.signal);
          } catch {
            return;
          }
        }
      }

      while (!controller.signal.aborted) {
        try {
          const afterSeq = cursorRef.current;
          await streamRunEvents({
            runId,
            afterSeq,
            lastEventId: afterSeq || undefined,
            signal: controller.signal,
            onOpen: () => {
              if (!mounted) return;
              setConnection("Live");
              setStreamError(null);
            },
            onEvent: (event) => {
              if (!mounted) return;

              const current = cursorRef.current;
              if (event.seq <= current) return;

              if (event.seq > current + 1) {
                void getRunTimeline(runId, current, 1000, controller.signal)
                  .then((page) => {
                    if (!mounted) return;
                    setEvents((previous) => {
                      const bySeq = new Map(previous.map((item) => [item.seq, item]));
                      for (const item of page.events) bySeq.set(item.seq, item);
                      return [...bySeq.values()].sort((a, b) => a.seq - b.seq);
                    });
                    cursorRef.current = Math.max(
                      cursorRef.current,
                      page.next_cursor,
                    );
                  })
                  .catch(() => {
                    // A full reconnect below remains the authoritative recovery path.
                  });
              } else {
                cursorRef.current = event.seq;
                setEvents((previous) => [...previous, event]);
              }

              void refreshState(controller.signal).catch(() => {
                // Persisted state is retried on reconnect if this refresh fails.
              });
            },
          });

          if (!controller.signal.aborted) {
            throw new Error("stream-closed");
          }
        } catch (error) {
          if (!mounted || isAbortError(error)) return;

          setConnection("Reconnecting");
          setStreamError(
            "Поток событий прервалась. Восстанавливаемся из сохранённого состояние продукта.",
          );

          try {
            await abortableDelay(1200, controller.signal);
            const [snapshot, backfill] = await Promise.all([
              getScenario2State(runId, controller.signal),
              getRunTimeline(runId, cursorRef.current, 1000, controller.signal),
            ]);
            if (!mounted) return;

            setState(snapshot);
            setEvents((previous) => {
              const bySeq = new Map(previous.map((item) => [item.seq, item]));
              for (const item of backfill.events) bySeq.set(item.seq, item);
              return [...bySeq.values()].sort((a, b) => a.seq - b.seq);
            });
            cursorRef.current = Math.max(
              cursorRef.current,
              backfill.next_cursor,
            );
          } catch (recoveryError) {
            if (isAbortError(recoveryError)) return;
            setConnection("Offline/Unavailable");
            setStreamError(displayApiError(recoveryError));
          }
        }
      }
    }

    void loadInitial();

    return () => {
      mounted = false;
      controller.abort();
    };
  }, [refreshState, runId]);

  const signalCount = state?.operational_signals.length ?? 0;
  const simulatorComplete = signalCount >= CANONICAL_SIGNAL_COUNT;
  const latestSignalAt = state?.operational_signals.at(-1)?.received_at ?? null;
  const autoScheduleAnchor = latestSignalAt ?? state?.run.created_at ?? null;

  useEffect(() => {
    if (
      !state ||
      simulatorComplete ||
      !autoScheduleAnchor ||
      autoAdvanceInFlightRef.current
    ) {
      return;
    }

    const anchorMs = Date.parse(autoScheduleAnchor);
    const delayMs = Number.isFinite(anchorMs)
      ? Math.max(0, anchorMs + AUTO_SIGNAL_INTERVAL_MS - Date.now())
      : AUTO_SIGNAL_INTERVAL_MS;
    const controller = new AbortController();

    const timeoutId = window.setTimeout(() => {
      if (controller.signal.aborted || autoAdvanceInFlightRef.current) return;
      autoAdvanceInFlightRef.current = true;
      setProgressNotice(null);

      void advanceScenario2Simulator(runId, controller.signal)
        .then((result) => {
          if (controller.signal.aborted) return;
          setState(result.state);
          setProgressNotice(
            result.ingested
              ? `Сигнал ${result.ingested.signal.source_ref} сохранён. Состояние продукта обновлено.`
              : result.complete
                ? "Все демонстрационные сигналы уже сохранены."
                : "Автоматический шаг симуляции выполнен.",
          );
        })
        .catch((error) => {
          if (controller.signal.aborted || isAbortError(error)) return;
          setProgressNotice(displayApiError(error));
        })
        .finally(() => {
          autoAdvanceInFlightRef.current = false;
        });
    }, delayMs);

    return () => {
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, [autoScheduleAnchor, runId, signalCount, simulatorComplete]);

  async function handleDecision(
    proposal: MajorIncidentProposalView,
    verb: "approve" | "reject",
  ) {
    if (decision) return;
    setDecision({ proposalId: proposal.proposal_id, verb });
    setDecisionError(null);
    setDecisionNotice(null);

    try {
      const result = await decideScenario2Proposal(
        runId,
        proposal.proposal_id,
        verb,
        DEMO_OPERATOR,
      );
      setDecisionNotice(
        result.replayed
          ? "Сохранённое решение воспроизведено без повторного выполнения."
          : "Решение человека сохранено в состоянии продукта.",
      );
      await refreshState();
    } catch (error) {
      try {
        const recovered = await refreshState();
        const persisted = recovered.major_incident_proposals.find(
          (item) => item.proposal_id === proposal.proposal_id,
        );
        if (persisted && persisted.status !== "PENDING_APPROVAL") {
          setDecisionNotice(
            "Ответ прервался, но сохранённое решение восстановлено из состояния продукта.",
          );
        } else {
          setDecisionError(
            `${displayApiError(error)} Сохранённое состояние всё ещё ожидает решения; повтор безопасен.`,
          );
        }
      } catch {
        setDecisionError(
          "Не удалось подтвердить результат решения. После восстановления соединения интерфейс перечитает состояние продукта.",
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
          <h1>Не удалось загрузить состояние продукта</h1>
          <p>{pageError ?? "API продукта не вернул состояние Сценария 2."}</p>
          <Link className="secondary-button" href="/">
            К выбору сценариев
          </Link>
        </div>
      </main>
    );
  }

  const selectedIncident = selectedIncidentId
    ? state.service_incidents.find(
        (item) => item.incident_id === selectedIncidentId,
      ) ?? null
    : null;
  const selectedObservation = selectedObservationId
    ? state.evidence.find((item) => item.evidence_id === selectedObservationId) ??
      null
    : null;
  const latestProposal = state.major_incident_proposals.length
    ? [...state.major_incident_proposals]
        .sort((a, b) => a.created_at.localeCompare(b.created_at))
        .at(-1) ?? null
    : null;
  const latestMajorIncident = state.major_incidents.at(-1) ?? null;
  const lastSeq = events.at(-1)?.seq ?? state.latest_event_seq;

  return (
    <main className="console-shell">
      <header className="run-header">
        <div className="brand-lockup">
          <Link href="/" className="brand-mark" aria-label="На главную">
            8O
          </Link>
          <div>
            <p className="eyebrow">Автономный L1-агент по инцидентам</p>
            <h1>Сценарий 2 · массовый сервисный инцидент</h1>
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
            <span>Статус</span>
            <StatusBadge value={state.run.status} tone="info" />
          </div>
          <div>
            <span>Инциденты</span>
            <strong>{state.service_incidents.length}</strong>
          </div>
          <div>
            <span>Сигналы</span>
            <strong>{state.operational_signals.length}</strong>
          </div>
          <div>
            <span>Соединение</span>
            <span
              className="status-badge"
              data-tone={connectionTone(connection)}
            >
              {connectionLabel(connection)}
            </span>
          </div>
          <div>
            <span>Последнее событие</span>
            <strong>#{lastSeq}</strong>
          </div>
        </div>
      </header>

      {streamError ? (
        <div className="connection-warning" role="status">
          Сохранённое состояние остаётся доступным. <span>{streamError}</span>
        </div>
      ) : null}

      <div className="console-grid">
        <section className="console-column">
          <article className="panel scroll-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Текущее состояние продукта</p>
                <h2>Инциденты</h2>
              </div>
              {selectedIncident ? (
                <StatusBadge
                  value={selectedIncident.status}
                  tone="info"
                />
              ) : (
                <span className="panel-count">
                  {state.service_incidents.length}
                </span>
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
                  <div className="wide">
                    <dt>ID инцидента</dt>
                    <dd><code>{selectedIncident.incident_id}</code></dd>
                  </div>
                  <div>
                    <dt>Площадка</dt>
                    <dd>{selectedIncident.site_id}</dd>
                  </div>
                  <div>
                    <dt>Статус</dt>
                    <dd>{statusLabel(selectedIncident.status)}</dd>
                  </div>
                  <div>
                    <dt>Сервис</dt>
                    <dd>{selectedIncident.service_key}</dd>
                  </div>
                  <div>
                    <dt>Симптом</dt>
                    <dd>{selectedIncident.symptom_key}</dd>
                  </div>
                  <div className="wide">
                    <dt>Обновлён</dt>
                    <dd>{formatTimestamp(selectedIncident.updated_at)}</dd>
                  </div>
                </dl>
              </div>
            ) : state.service_incidents.length ? (
              <div className="entity-list" role="list">
                {state.service_incidents.map((item) => (
                  <div
                    className="entity-row"
                    role="listitem"
                    key={item.incident_id}
                  >
                    <div className="entity-row-main">
                      <strong>{item.symptom_key}</strong>
                      <span>{item.site_id} · {item.service_key}</span>
                    </div>
                    <StatusBadge value={item.status} tone="info" />
                    <button
                      className="detail-button"
                      type="button"
                      onClick={() => setSelectedIncidentId(item.incident_id)}
                    >
                      Подробнее
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyPanel>Инцидентов ещё нет.</EmptyPanel>
            )}
          </article>

          <article className="panel scroll-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Безопасные факты продукта</p>
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
                      <li key={fact}>{fact}</li>
                    ))}
                  </ul>
                ) : null}
                <div className="observation-payload">
                  <span className="subtle-label payload-label">
                    Безопасные типизированные данные
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
                      <span>{evidence.entity_ids[0] ?? "наблюдение"}</span>
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
                        setSelectedObservationId(evidence.evidence_id)
                      }
                    >
                      Подробнее
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyPanel>
                Наблюдения появятся после того, как агент начнёт расследование.
              </EmptyPanel>
            )}
          </article>
        </section>

        <section className="console-column timeline-column">
          <article className="panel scroll-panel timeline-panel">
            <div className="panel-heading sticky-heading">
              <div>
                <p className="panel-kicker">Сохранённый журнал аудита</p>
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
                        <strong>{eventSummary(event)}</strong>
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
              <EmptyPanel>Сохранённых событий пока нет.</EmptyPanel>
            )}
          </article>
        </section>

        <section className="console-column">
          <article className="panel scroll-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Корреляция и решение</p>
                <h2>Предложение крупного инцидента</h2>
              </div>
              {latestProposal ? (
                <StatusBadge
                  value={latestProposal.status}
                  tone={proposalTone(latestProposal.status)}
                />
              ) : null}
            </div>

            <div className="scenario-progress">
              <div>
                <span className="subtle-label">Автоматическая симуляция</span>
                <p>
                  Сигналы поступают автоматически каждые 20 секунд. Сохранено:{" "}
                  <strong>{state.operational_signals.length}</strong> из{" "}
                  <strong>{CANONICAL_SIGNAL_COUNT}</strong>.
                </p>
              </div>
              {progressNotice ? (
                <p className="decision-notice" role="status">
                  {progressNotice}
                </p>
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
                    <dt>Зависимость</dt>
                    <dd>{latestProposal.dependency_name}</dd>
                  </div>
                  <div>
                    <dt>Действие</dt>
                    <dd>{latestProposal.action_type}</dd>
                  </div>
                  <div className="wide">
                    <dt>Затронутые площадки</dt>
                    <dd>{latestProposal.affected_site_ids.join(" · ")}</dd>
                  </div>
                </dl>

                <div className="proposal-rationale">
                  <span>Обоснование</span>
                  <p>{majorIncidentRationale(latestProposal)}</p>
                </div>

                <div className="proposal-evidence">
                  <span className="subtle-label">ID наблюдений</span>
                  <div className="chip-row">
                    {latestProposal.evidence_ids.map((id) => (
                      <code key={id}>{id}</code>
                    ))}
                  </div>
                </div>

                {latestProposal.status === "PENDING_APPROVAL" ? (
                  <div className="decision-area">
                    <p>
                      Для создания крупного инцидента требуется решение человека.
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
                        {decision?.verb === "approve"
                          ? "Одобряем…"
                          : "Одобрить"}
                      </button>
                      <button
                        className="reject-button"
                        type="button"
                        disabled={decision !== null}
                        onClick={() =>
                          void handleDecision(latestProposal, "reject")
                        }
                      >
                        {decision?.verb === "reject"
                          ? "Отклоняем…"
                          : "Отклонить"}
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
                Предложения пока нет. Агент создаст его только после достаточного
                набора сохранённых наблюдений.
              </EmptyPanel>
            )}
          </article>

          <article className="panel scroll-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Результат после решения человека</p>
                <h2>Крупный инцидент</h2>
              </div>
              <span className="panel-count">{state.major_incidents.length}</span>
            </div>

            {latestMajorIncident ? (
              <div className="work-order-card">
                <div className="work-order-heading">
                  <StatusBadge value={latestMajorIncident.status} tone="executed" />
                  <code>{latestMajorIncident.major_incident_id}</code>
                </div>
                <dl className="facts-grid">
                  <div>
                    <dt>Сервис</dt>
                    <dd>{latestMajorIncident.service_key}</dd>
                  </div>
                  <div>
                    <dt>Зависимость</dt>
                    <dd>{latestMajorIncident.dependency_name}</dd>
                  </div>
                  <div className="wide">
                    <dt>Площадки</dt>
                    <dd>{latestMajorIncident.affected_site_ids.join(" · ")}</dd>
                  </div>
                  <div className="wide">
                    <dt>Описание</dt>
                    <dd>{latestMajorIncident.summary}</dd>
                  </div>
                  <div className="wide">
                    <dt>Создан</dt>
                    <dd>{formatTimestamp(latestMajorIncident.created_at)}</dd>
                  </div>
                </dl>
                <p className="semantic-note">
                  Крупный инцидент зарегистрирован как демонстрационное действие продукта.
                  Это не изменение реальной клиентской инфраструктуры.
                </p>
              </div>
            ) : (
              <EmptyPanel>
                Крупный инцидент ещё не создан. До человеческого решения побочный
                эффект запрещён.
              </EmptyPanel>
            )}
          </article>
        </section>
      </div>

      <footer className="console-footer">
        <span>Источник истины: состояние продукта в PostgreSQL</span>
        <span>Поток событий: сохранённый SSE</span>
        <span>Среда AI: Google ADK + Gemini</span>
      </footer>
    </main>
  );
}
