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
  actionTypeLabel,
  activityKindLabel,
  connectionLabel,
  connectionTone,
  eventSummary,
  eventTypeLabel,
  evidenceSourceLabel,
  formatTimestamp,
  incidentTextLabel,
  majorIncidentRationale,
  observationState,
  playbackIncidentStatus,
  playbackVisibility,
  proposalTone,
  serviceLabel,
  statusLabel,
  STALE_PROPOSAL_NOTE,
  scenario2InvestigationActivities,
  visibleTimelineEvents,
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
  const [playbackNow, setPlaybackNow] = useState(() => Date.now());
  const [connection, setConnection] =
    useState<ConnectionState>("Reconnecting");
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [decision, setDecision] = useState<{
    proposalId: string;
    verb: "approve" | "reject";
  } | null>(null);
  const [decisionNotice, setDecisionNotice] = useState<string | null>(null);
  const [journalVisible, setJournalVisible] = useState(false);
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
            "Поток событий прервался. Восстанавливаемся из сохранённого состояния продукта.",
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

  useEffect(() => {
    setJournalVisible(false);
  }, [runId]);

  useEffect(() => {
    const timerId = window.setInterval(() => {
      setPlaybackNow(Date.now());
    }, 1_000);

    return () => window.clearInterval(timerId);
  }, [runId]);

  const signalCount = state?.operational_signals.length ?? 0;
  const simulatorComplete = signalCount >= CANONICAL_SIGNAL_COUNT;
  const latestSignalAt = state?.operational_signals.at(-1)?.received_at ?? null;
  const autoScheduleAnchor = latestSignalAt ?? state?.run.created_at ?? null;

  useEffect(() => {
    if (
      simulatorComplete ||
      !autoScheduleAnchor ||
      autoAdvanceInFlightRef.current
    ) {
      return;
    }

    const anchorMs = Date.parse(autoScheduleAnchor);
    const delayMs =
      signalCount === 0
        ? 0
        : Number.isFinite(anchorMs)
          ? Math.max(0, anchorMs + AUTO_SIGNAL_INTERVAL_MS - Date.now())
          : AUTO_SIGNAL_INTERVAL_MS;
    const controller = new AbortController();

    const timeoutId = window.setTimeout(() => {
      if (controller.signal.aborted || autoAdvanceInFlightRef.current) return;
      autoAdvanceInFlightRef.current = true;
      void advanceScenario2Simulator(runId, controller.signal)
        .then((result) => {
          if (controller.signal.aborted) return;
          setState(result.state);
        })
        .catch((error) => {
          if (controller.signal.aborted || isAbortError(error)) return;
          setStreamError(displayApiError(error));
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

  const visibleEvents = visibleTimelineEvents(
    events,
    state.run.created_at,
    playbackNow,
  );
  const investigationActivities = scenario2InvestigationActivities(
    visibleEvents,
    state,
  );
  const playback = playbackVisibility(visibleEvents);
  const visibleServiceIncidents = state.service_incidents.filter((item) =>
    playback.signalSites.has(item.site_id),
  );
  const visibleEvidence = state.evidence.filter((item) =>
    playback.evidenceIds.has(item.evidence_id),
  );
  const visibleProposals = state.major_incident_proposals.filter((item) =>
    playback.proposalIds.has(item.proposal_id),
  );
  const visibleMajorIncidents = playback.actionExecuted
    ? state.major_incidents
    : [];

  const selectedIncident = selectedIncidentId
    ? visibleServiceIncidents.find(
        (item) => item.incident_id === selectedIncidentId,
      ) ?? null
    : null;
  const selectedObservation = selectedObservationId
    ? visibleEvidence.find((item) => item.evidence_id === selectedObservationId) ??
      null
    : null;
  const latestProposal = visibleProposals.length
    ? [...visibleProposals]
        .sort((a, b) => a.created_at.localeCompare(b.created_at))
        .at(-1) ?? null
    : null;
  const latestProposalDisplayStatus = latestProposal
    ? playback.actionExecuted
      ? latestProposal.status
      : !playback.approvalDecided
        ? "PENDING_APPROVAL"
        : playback.approvalDecision === "REJECTED"
          ? "REJECTED"
          : latestProposal.status === "STALE"
            ? "STALE"
            : playback.approvalDecision === "APPROVED"
              ? "APPROVED"
              : latestProposal.status
    : null;
  const latestMajorIncident = visibleMajorIncidents.at(-1) ?? null;

  return (
    <main className="console-shell">
      {streamError ? (
        <div className="connection-warning" role="status">
          Сохранённое состояние остаётся доступным. <span>{streamError}</span>
        </div>
      ) : null}

      <div className="console-grid">
        <section className="console-column">
          <article className="panel scroll-panel incident-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Текущее состояние продукта</p>
                <h2>Инциденты</h2>
              </div>
              {selectedIncident ? (
                <StatusBadge
                  value={playbackIncidentStatus(
                    selectedIncident.status,
                    playback.actionExecuted,
                  )}
                  tone="info"
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
                    <dd>
                      {statusLabel(
                        playbackIncidentStatus(
                          selectedIncident.status,
                          playback.actionExecuted,
                        ),
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>Сервис</dt>
                    <dd>{serviceLabel(selectedIncident.service_key)}</dd>
                  </div>
                  <div>
                    <dt>Симптом</dt>
                    <dd>{incidentTextLabel(selectedIncident.symptom_key)}</dd>
                  </div>
                  <div className="wide">
                    <dt>Обновлён</dt>
                    <dd>{formatTimestamp(selectedIncident.updated_at)}</dd>
                  </div>
                </dl>
              </div>
            ) : visibleServiceIncidents.length ? (
              <div className="entity-list" role="list">
                {visibleServiceIncidents.map((item) => (
                  <div
                    className="entity-row"
                    role="listitem"
                    key={item.incident_id}
                  >
                    <div className="entity-row-main">
                      <strong>{incidentTextLabel(item.symptom_key)}</strong>
                      <span>{item.site_id} · {serviceLabel(item.service_key)}</span>
                    </div>
                    <StatusBadge
                      value={playbackIncidentStatus(
                        item.status,
                        playback.actionExecuted,
                      )}
                      tone="info"
                    />
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
                      <li key={fact}>{fact}</li>
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
                onClick={() => setJournalVisible((visible) => !visible)}
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

        <section className="console-column">
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
                    <dd>{actionTypeLabel(latestProposal.action_type)}</dd>
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

                {latestProposal.status === "PENDING_APPROVAL" &&
                playback.approvalRequested ? (
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

                {playback.approvalDecided &&
                latestProposal.status === "STALE" ? (
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

          <article className="panel scroll-panel result-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Результат действия</p>
                <h2>Что сделано</h2>
              </div>
              
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
                    <dd>{serviceLabel(latestMajorIncident.service_key)}</dd>
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
                    <dd>{incidentTextLabel(latestMajorIncident.summary)}</dd>
                  </div>
                  <div className="wide">
                    <dt>Создан</dt>
                    <dd>{formatTimestamp(latestMajorIncident.created_at)}</dd>
                  </div>
                </dl>
                <p className="semantic-note">
                  Крупный инцидент зарегистрирован.
                </p>
              </div>
            ) : null}
          </article>
        </section>
      </div>

      <footer className="run-footer-bar">
        <strong>Сценарий 2 · массовый сервисный инцидент</strong>
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
