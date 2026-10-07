import type {
  ApplicationEventView,
  ConnectionState,
  EvidenceView,
  JsonValue,
  MajorIncidentProposalView,
  ProposalView,
  RunStateResponse,
  Scenario2IngestionStateResponse,
} from "./types";

export const FIELD_SERVICE_OUTCOME_NOTE =
  "Заявка на выездной сервис зарегистрирована.";

export const TIMELINE_PLAYBACK_INTERVAL_MS = 5_000;

export type InvestigationActivityKind =
  | "fact"
  | "check"
  | "agent"
  | "human"
  | "result";

export type InvestigationActivity = {
  id: string;
  occurred_at: string;
  source_event_seq: number;
  kind: InvestigationActivityKind;
  title: string;
  detail: string | null;
};

export function visibleTimelineEvents(
  events: ApplicationEventView[],
  runStartedAt: string,
  nowMs: number,
): ApplicationEventView[] {
  const ordered = [...events].sort((a, b) => a.seq - b.seq);
  if (!ordered.length) return [];

  const startedMs = Date.parse(runStartedAt);
  if (!Number.isFinite(startedMs)) return ordered.reverse();

  const elapsedMs = Math.max(0, nowMs - startedMs);
  const visibleCount = Math.min(
    ordered.length,
    Math.floor(elapsedMs / TIMELINE_PLAYBACK_INTERVAL_MS) + 1,
  );

  return ordered.slice(0, visibleCount).reverse();
}

export type PlaybackVisibility = {
  evidenceIds: Set<string>;
  proposalIds: Set<string>;
  signalSites: Set<string>;
  approvalRequested: boolean;
  approvalDecided: boolean;
  actionExecuted: boolean;
};

export function playbackVisibility(
  visibleEvents: ApplicationEventView[],
): PlaybackVisibility {
  const evidenceIds = new Set<string>();
  const proposalIds = new Set<string>();
  const signalSites = new Set<string>();
  let approvalRequested = false;
  let approvalDecided = false;
  let actionExecuted = false;

  for (const event of visibleEvents) {
    if (event.event_type === "observation.recorded") {
      const evidenceId = stringValue(event.payload, "evidence_id");
      if (evidenceId) evidenceIds.add(evidenceId);
      continue;
    }

    if (event.event_type === "proposal.created") {
      const proposalId = stringValue(event.payload, "proposal_id");
      if (proposalId) proposalIds.add(proposalId);
      continue;
    }

    if (event.event_type === "external.signal") {
      const details = objectValue(event.payload, "details");
      const site =
        stringValue(event.payload, "site_id") ??
        (details ? stringValue(details, "site_id") : null);
      if (site) signalSites.add(site);
      continue;
    }

    if (
      event.event_type === "run.status_changed" &&
      stringValue(event.payload, "status") === "WAITING_APPROVAL"
    ) {
      approvalRequested = true;
      continue;
    }

    if (event.event_type === "approval.decided") {
      approvalDecided = true;
      continue;
    }

    if (event.event_type === "action.executed") {
      actionExecuted = true;
    }
  }

  return {
    evidenceIds,
    proposalIds,
    signalSites,
    approvalRequested,
    approvalDecided,
    actionExecuted,
  };
}

export function playbackIncidentStatus(
  status: string,
  actionExecuted: boolean,
): string {
  return !actionExecuted && status === "ESCALATED" ? "OPEN" : status;
}

export const STALE_PROPOSAL_NOTE =
  "Решение человека сохранено, но свежие авторитетные данные больше не разрешают выполнение. Действие выездного сервиса не создавалось.";

function stringValue(
  payload: Record<string, JsonValue>,
  key: string,
): string | null {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function booleanValue(
  payload: Record<string, JsonValue>,
  key: string,
): boolean | null {
  const value = payload[key];
  return typeof value === "boolean" ? value : null;
}

function objectValue(
  payload: Record<string, JsonValue>,
  key: string,
): Record<string, JsonValue> | null {
  const value = payload[key];
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value
    : null;
}

function stringArrayValue(
  payload: Record<string, JsonValue>,
  key: string,
): string[] {
  const value = payload[key];
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function evidenceForEvent(
  event: ApplicationEventView,
  evidence: EvidenceView[],
): EvidenceView | null {
  const evidenceId = stringValue(event.payload, "evidence_id");
  if (!evidenceId) return null;
  return evidence.find((item) => item.evidence_id === evidenceId) ?? null;
}

function activity(
  event: ApplicationEventView,
  kind: InvestigationActivityKind,
  title: string,
  detail: string | null = null,
): InvestigationActivity {
  return {
    id: `${event.seq}:${kind}:${title}`,
    occurred_at: event.occurred_at,
    source_event_seq: event.seq,
    kind,
    title,
    detail,
  };
}

export function activityKindLabel(kind: InvestigationActivityKind): string {
  if (kind === "fact") return "Факт";
  if (kind === "check") return "Результат проверки";
  if (kind === "agent") return "Вывод агента";
  if (kind === "human") return "Решение человека";
  return "Результат";
}

export function eventSummary(event: ApplicationEventView): string {
  const payload = event.payload;
  switch (event.event_type) {
    case "simulation.started":
      return "Запуск симуляции";
    case "external.signal":
      return "Получен операционный сигнал";
    case "observation.recorded": {
      const sourceType = stringValue(payload, "source_type");
      return sourceType
        ? `Сохранено наблюдение: ${sourceType}`
        : "Сохранено наблюдение";
    }
    case "tool.started": {
      const tool = stringValue(payload, "tool_name");
      return tool ? `Запущен инструмент: ${tool}` : "Запущен инструмент";
    }
    case "tool.finished":
      return "Инструмент завершил работу";
    case "finding.recorded":
      return "Сохранён вывод";
    case "proposal.created":
      return "Создано предложение на действие";
    case "approval.decided": {
      const decision = stringValue(payload, "decision");
      return decision
        ? `Сохранено решение человека: ${statusLabel(decision)}`
        : "Сохранено решение человека";
    }
    case "action.executed":
      return "Действие продукта зарегистрировано";
    case "run.status_changed": {
      const status = stringValue(payload, "status");
      return status
        ? `Статус запуска → ${statusLabel(status)}`
        : "Изменился статус запуска";
    }
    default:
      return event.event_type;
  }
}

export function observationState(evidence: EvidenceView): string | null {
  const payload = evidence.payload;
  for (const key of ["operational_state", "site_network", "status", "state"]) {
    const value = stringValue(payload, key);
    if (value) return value;
  }

  if (evidence.source_type === "KB_ARTICLE") {
    const approved = payload.approved;
    if (typeof approved === "boolean") {
      return approved ? "APPROVED" : "NOT_APPROVED";
    }
  }

  return null;
}

const STATUS_LABELS: Record<string, string> = {
  ACTIVE: "Активен",
  WAITING_APPROVAL: "Ожидает решения",
  PENDING_APPROVAL: "Ожидает решения",
  APPROVED: "Одобрено",
  REJECTED: "Отклонено",
  STALE: "Устарело",
  EXECUTED: "Выполнено",
  ESCALATED: "Эскалирован",
  OPEN: "Открыт",
  CLOSED: "Закрыт",
  REGISTERED: "Зарегистрирован",
  HEALTHY: "Исправно",
  DEGRADED: "Деградация",
  DOWN: "Недоступно",
  UNKNOWN: "Неизвестно",
  NOT_APPROVED: "Не одобрено",
};

export function statusLabel(value: string): string {
  return STATUS_LABELS[value] ?? value;
}

const DIAGNOSIS_LABELS: Record<string, string> = {
  LOCAL_ACCESS_LINK_FAILURE: "Сбой локального канала доступа",
};

const ACTION_TYPE_LABELS: Record<string, string> = {
  ONSITE_FIELD_VISIT: "Выезд специалиста на площадку",
  FIELD_SERVICE_VISIT: "Выезд специалиста на площадку",
  CREATE_MAJOR_INCIDENT: "Создание крупного инцидента",
  REGISTER_MAJOR_INCIDENT: "Регистрация крупного инцидента",
  MAJOR_INCIDENT_CREATE: "Создание крупного инцидента",
  MAJOR_INCIDENT_REGISTRATION: "Регистрация крупного инцидента",
};

export function diagnosisLabel(value: string): string {
  return DIAGNOSIS_LABELS[value] ?? "Диагноз сформирован агентом";
}

export function actionTypeLabel(value: string): string {
  return ACTION_TYPE_LABELS[value] ?? "Действие агента";
}

function standardEvidenceActivity(
  event: ApplicationEventView,
  evidence: EvidenceView,
): InvestigationActivity | null {
  const payload = evidence.payload;

  switch (evidence.source_type) {
    case "CMDB_SNAPSHOT": {
      const device = stringValue(payload, "device_id");
      const switchId = stringValue(payload, "expected_switch_id");
      const port = stringValue(payload, "expected_port_id");
      const detail =
        device && switchId && port
          ? `Устройство ${device} подключено к ${switchId}, порт ${port}.`
          : "Получены данные о подключении устройства к инфраструктуре.";
      return activity(event, "check", "Агент определил топологию устройства", detail);
    }
    case "SITE_HEALTH": {
      const site = stringValue(payload, "site_id");
      const siteNetwork = stringValue(payload, "site_network");
      const paymentService = stringValue(payload, "payment_service");
      const peerReachable = booleanValue(payload, "peer_reachable");
      const detail =
        siteNetwork === "HEALTHY" &&
        paymentService === "HEALTHY" &&
        peerReachable === true
          ? `Сеть и платёжный сервис${site ? ` на площадке ${site}` : ""} работают штатно; соседнее устройство доступно.`
          : `Получено актуальное состояние площадки${site ? ` ${site}` : ""}.`;
      return activity(event, "check", "Агент проверил состояние площадки", detail);
    }
    case "ACCESS_LINK_DIAGNOSTIC": {
      const switchId = stringValue(payload, "switch_id");
      const port = stringValue(payload, "port_id");
      const adminState = stringValue(payload, "admin_state");
      const operationalState = stringValue(payload, "operational_state");
      if (operationalState === "DOWN") {
        return activity(
          event,
          "check",
          "Обнаружен локальный сетевой сбой",
          `Канал ${switchId && port ? `${switchId} / ${port}` : "доступа"} административно ${adminState === "UP" ? "включён" : statusLabel(adminState ?? "UNKNOWN")}, но операционно недоступен.`,
        );
      }
      return activity(
        event,
        "check",
        "Агент проверил локальный канал доступа",
        operationalState
          ? `Операционное состояние канала: ${statusLabel(operationalState)}.`
          : null,
      );
    }
    case "INCIDENT_SEARCH": {
      const openIds = stringArrayValue(payload, "open_incident_ids");
      return activity(
        event,
        "check",
        "Агент проверил связанные инциденты",
        openIds.length
          ? `Найдены открытые инциденты: ${openIds.join(", ")}.`
          : "Других открытых инцидентов по проверенной области не найдено.",
      );
    }
    case "KB_ARTICLE": {
      const approved = booleanValue(payload, "approved");
      const title = stringValue(payload, "title");
      return activity(
        event,
        "check",
        approved
          ? "Агент нашёл утверждённую инструкцию"
          : "Агент проверил базу знаний",
        title ? `Материал: «${title}».` : null,
      );
    }
    case "SERVICE_DEPENDENCY_MAPPING": {
      const service = stringValue(payload, "service_key");
      const dependency = stringValue(payload, "dependency_name");
      return activity(
        event,
        "check",
        "Агент определил внешнюю зависимость сервиса",
        dependency
          ? `Сервис ${service ?? "в текущем инциденте"} зависит от ${dependency}.`
          : null,
      );
    }
    case "EXTERNAL_DEPENDENCY_STATUS": {
      const dependency = stringValue(payload, "dependency_name");
      const status = stringValue(payload, "status");
      return activity(
        event,
        "check",
        `Агент проверил состояние ${dependency ?? "внешней зависимости"}`,
        status ? `Состояние: ${statusLabel(status)}.` : null,
      );
    }
    case "LOCAL_SERVICE_HEALTH": {
      const site = stringValue(payload, "site_id");
      const network = stringValue(payload, "network_health");
      const localService = stringValue(payload, "local_service_health");
      return activity(
        event,
        "check",
        "Агент проверил локальную инфраструктуру",
        network === "HEALTHY" && localService === "HEALTHY"
          ? `Локальная сеть и сервис${site ? ` на площадке ${site}` : ""} работают штатно.`
          : null,
      );
    }
    case "MAJOR_INCIDENT_SEARCH": {
      const openIds = stringArrayValue(payload, "open_major_incident_ids");
      return activity(
        event,
        "check",
        "Агент проверил существующие крупные инциденты",
        openIds.length
          ? `Найдены совпадающие крупные инциденты: ${openIds.join(", ")}.`
          : "Совпадающий открытый крупный инцидент не найден.",
      );
    }
    default:
      return activity(
        event,
        "check",
        "Агент получил новое подтверждённое наблюдение",
        `Тип наблюдения: ${evidence.source_type}.`,
      );
  }
}

function standardExternalSignalActivity(
  event: ApplicationEventView,
  state: RunStateResponse,
): InvestigationActivity {
  const details = objectValue(event.payload, "details");
  const incidentId =
    (details && stringValue(details, "incident_id")) ??
    stringValue(event.payload, "incident_id");
  const incident =
    state.incidents.find((item) => item.incident_id === incidentId) ??
    state.incidents[0] ??
    null;
  const device =
    (details && stringValue(details, "reported_device_id")) ??
    incident?.reported_device_id ??
    null;
  const site =
    (details && stringValue(details, "site_id")) ?? incident?.site_id ?? null;

  const symptomKey = details ? stringValue(details, "symptom_key") : null;
  const signalTitle =
    state.run.scenario_id === "scenario-3" ||
    symptomKey === "payment_gateway_timeout"
      ? `Получен сигнал: таймауты платежей${device ? ` на терминале ${device}` : ""}`
      : device
        ? `Получен сигнал: терминал ${device} недоступен`
        : "Получен сигнал об инциденте";

  return activity(
    event,
    "fact",
    signalTitle,
    site
      ? `Инцидент зарегистрирован на площадке ${site}.`
      : "Инцидент зарегистрирован в состоянии продукта.",
  );
}

export function standardInvestigationActivities(
  visibleEvents: ApplicationEventView[],
  state: RunStateResponse,
): InvestigationActivity[] {
  const ordered = [...visibleEvents].sort((a, b) => a.seq - b.seq);
  const result: InvestigationActivity[] = [];
  let investigationStarted = false;

  for (const event of ordered) {
    if (event.event_type === "external.signal") {
      result.push(standardExternalSignalActivity(event, state));
      continue;
    }

    if (event.event_type === "tool.started" && !investigationStarted) {
      investigationStarted = true;
      result.push(
        activity(
          event,
          "agent",
          "Агент приступил к расследованию",
          "Начат сбор и проверка фактов по инциденту.",
        ),
      );
      continue;
    }

    if (event.event_type === "observation.recorded") {
      const evidence = evidenceForEvent(event, state.evidence);
      if (evidence) {
        const item = standardEvidenceActivity(event, evidence);
        if (item) result.push(item);
      }
      continue;
    }

    if (event.event_type === "finding.recorded") {
      const summary =
        stringValue(event.payload, "summary") ??
        stringValue(event.payload, "finding");
      result.push(
        activity(
          event,
          "agent",
          "Агент зафиксировал диагностический вывод",
          summary,
        ),
      );
      continue;
    }

    if (event.event_type === "proposal.created") {
      const proposalId = stringValue(event.payload, "proposal_id");
      const proposal =
        state.proposals.find((item) => item.proposal_id === proposalId) ?? null;
      result.push(
        activity(
          event,
          "agent",
          "Агент сформировал предложение действия",
          proposal
            ? `Диагноз: ${diagnosisLabel(proposal.diagnosis)}. Предложение: ${actionTypeLabel(proposal.action_type)}.`
            : "Предложение сохранено в состоянии продукта.",
        ),
      );
      continue;
    }

    if (
      event.event_type === "run.status_changed" &&
      stringValue(event.payload, "status") === "WAITING_APPROVAL"
    ) {
      result.push(
        activity(
          event,
          "agent",
          "Агент запросил подтверждение действия",
          "Для потенциально опасного действия требуется решение администратора.",
        ),
      );
      continue;
    }

    if (event.event_type === "approval.decided") {
      const decision = stringValue(event.payload, "decision");
      result.push(
        activity(
          event,
          "human",
          decision === "APPROVED"
            ? "Администратор одобрил предложенное действие"
            : decision === "REJECTED"
              ? "Администратор отклонил предложенное действие"
              : "Получено решение администратора",
          null,
        ),
      );
      continue;
    }

    if (event.event_type === "action.executed") {
      result.push(
        activity(
          event,
          "result",
          FIELD_SERVICE_OUTCOME_NOTE,
          null,
        ),
      );
    }
  }

  return result.reverse();
}

function scenario2SignalActivity(
  event: ApplicationEventView,
): InvestigationActivity {
  const source = stringValue(event.payload, "source");
  const site = stringValue(event.payload, "site_id");
  const service = stringValue(event.payload, "service_key");
  const safePayload = objectValue(event.payload, "safe_payload");
  const kind = safePayload ? stringValue(safePayload, "kind") : null;
  const impact = safePayload ? stringValue(safePayload, "impact") : null;

  if (source === "MONITORING") {
    const description =
      kind === "payment_timeout_rate"
        ? "повышенный уровень таймаутов платежей"
        : `сбой сервиса ${service ?? "платежей"}`;
    return activity(
      event,
      "fact",
      `Получен сигнал мониторинга: ${description}${site ? ` на площадке ${site}` : ""}`,
      null,
    );
  }

  if (source === "ITSM") {
    const description =
      impact === "payment_attempts_timing_out" || kind === "user_ticket"
        ? "платёжные операции завершаются по таймауту"
        : `зафиксирована проблема сервиса ${service ?? "платежей"}`;
    return activity(
      event,
      "fact",
      `Получена заявка пользователя: ${description}${site ? ` на площадке ${site}` : ""}`,
      null,
    );
  }

  return activity(
    event,
    "fact",
    `Получен операционный сигнал: зафиксирована проблема сервиса ${service ?? "платежей"}${site ? ` на площадке ${site}` : ""}`,
    null,
  );
}

function scenario2EvidenceActivity(
  event: ApplicationEventView,
  evidence: EvidenceView,
): InvestigationActivity | null {
  const payload = evidence.payload;

  switch (evidence.source_type) {
    case "LOCAL_SERVICE_HEALTH": {
      const site = stringValue(payload, "site_id");
      const network = stringValue(payload, "network_health");
      const localService = stringValue(payload, "local_service_health");
      return activity(
        event,
        "check",
        "Агент проверил локальную инфраструктуру",
        network === "HEALTHY" && localService === "HEALTHY"
          ? `Локальная сеть и платёжный сервис${site ? ` на площадке ${site}` : ""} работают штатно.`
          : `Получено актуальное состояние${site ? ` площадки ${site}` : " локальной инфраструктуры"}.`,
      );
    }
    case "SERVICE_DEPENDENCY_MAPPING": {
      const service = stringValue(payload, "service_key");
      const dependency = stringValue(payload, "dependency_name");
      return activity(
        event,
        "check",
        "Агент определил общую внешнюю зависимость",
        dependency
          ? `Сервис ${service ?? "платежей"} зависит от ${dependency}.`
          : null,
      );
    }
    case "EXTERNAL_DEPENDENCY_STATUS": {
      const dependency = stringValue(payload, "dependency_name");
      const status = stringValue(payload, "status");
      return activity(
        event,
        "check",
        status === "DEGRADED"
          ? `Обнаружена деградация ${dependency ?? "внешней зависимости"}`
          : `Агент проверил состояние ${dependency ?? "внешней зависимости"}`,
        status ? `Состояние: ${statusLabel(status)}.` : null,
      );
    }
    case "MAJOR_INCIDENT_SEARCH": {
      const openIds = stringArrayValue(payload, "open_major_incident_ids");
      return activity(
        event,
        "check",
        "Агент проверил существующие крупные инциденты",
        openIds.length
          ? `Найдены совпадающие открытые инциденты: ${openIds.join(", ")}.`
          : "Совпадающий открытый крупный инцидент не найден.",
      );
    }
    case "OPERATIONAL_SIGNAL":
      return null;
    default:
      return standardEvidenceActivity(event, evidence);
  }
}

export function scenario2InvestigationActivities(
  visibleEvents: ApplicationEventView[],
  state: Scenario2IngestionStateResponse,
): InvestigationActivity[] {
  const ordered = [...visibleEvents].sort((a, b) => a.seq - b.seq);
  const result: InvestigationActivity[] = [];
  let investigationStarted = false;

  for (const event of ordered) {
    if (event.event_type === "external.signal") {
      result.push(scenario2SignalActivity(event));
      continue;
    }

    if (event.event_type === "tool.started" && !investigationStarted) {
      investigationStarted = true;
      result.push(
        activity(
          event,
          "agent",
          "Агент приступил к проверке собранных фактов",
          "Начата проверка локального состояния и общих зависимостей.",
        ),
      );
      continue;
    }

    if (event.event_type === "observation.recorded") {
      const evidence = evidenceForEvent(event, state.evidence);
      if (evidence) {
        const item = scenario2EvidenceActivity(event, evidence);
        if (item) result.push(item);
      }
      continue;
    }

    if (event.event_type === "proposal.created") {
      const proposalId = stringValue(event.payload, "proposal_id");
      const proposal =
        state.major_incident_proposals.find(
          (item) => item.proposal_id === proposalId,
        ) ?? null;
      result.push(
        activity(
          event,
          "agent",
          "Агент выявил корреляцию между событиями",
          proposal
            ? `Сбои на площадках ${proposal.affected_site_ids.join(", ")} связаны с общей деградацией зависимости ${proposal.dependency_name}. Агент предлагает зарегистрировать крупный инцидент.`
            : "Корреляция подтверждена сохранённым предложением крупного инцидента.",
        ),
      );
      continue;
    }

    if (
      event.event_type === "run.status_changed" &&
      stringValue(event.payload, "status") === "WAITING_APPROVAL"
    ) {
      result.push(
        activity(
          event,
          "agent",
          "Агент запросил подтверждение действия",
          "Для регистрации крупного инцидента требуется решение администратора.",
        ),
      );
      continue;
    }

    if (event.event_type === "approval.decided") {
      const decision = stringValue(event.payload, "decision");
      result.push(
        activity(
          event,
          "human",
          decision === "APPROVED"
            ? "Администратор одобрил создание крупного инцидента"
            : decision === "REJECTED"
              ? "Администратор отклонил создание крупного инцидента"
              : "Получено решение администратора",
          null,
        ),
      );
      continue;
    }

    if (event.event_type === "action.executed") {
      const majorIncidentId = stringValue(event.payload, "major_incident_id");
      result.push(
        activity(
          event,
          "result",
          "Крупный инцидент зарегистрирован",
          majorIncidentId ? `ID крупного инцидента: ${majorIncidentId}.` : null,
        ),
      );
    }
  }

  return result.reverse();
}

export function proposalRationale(proposal: ProposalView): string {
  if (proposal.diagnosis === "LOCAL_ACCESS_LINK_FAILURE") {
    return `Терминал ${proposal.device_id} недоступен из-за локального сбоя канала доступа. Наблюдения подтверждают необходимость выездной диагностики; действие требует решения человека.`;
  }
  return proposal.rationale;
}

export function majorIncidentRationale(
  proposal: MajorIncidentProposalView,
): string {
  const sites = proposal.affected_site_ids.join(", ");
  return `Сигналы на площадках ${sites} указывают на общую деградацию зависимости ${proposal.dependency_name}. Предлагается зарегистрировать крупный инцидент после подтверждения человеком.`;
}

export function connectionLabel(state: ConnectionState): string {
  if (state === "Live") return "Онлайн";
  if (state === "Reconnecting") return "Переподключение";
  return "Недоступно";
}

export function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return (
    new Intl.DateTimeFormat("ru-RU", {
      dateStyle: "medium",
      timeStyle: "medium",
      timeZone: "UTC",
    }).format(date) + " UTC"
  );
}

export function proposalTone(
  status: ProposalView["status"] | string,
): "pending" | "rejected" | "stale" | "executed" | "neutral" {
  if (status === "PENDING_APPROVAL") return "pending";
  if (status === "REJECTED") return "rejected";
  if (status === "STALE") return "stale";
  if (status === "EXECUTED") return "executed";
  return "neutral";
}

export function connectionTone(
  state: ConnectionState,
): "live" | "waiting" | "offline" {
  if (state === "Live") return "live";
  if (state === "Reconnecting") return "waiting";
  return "offline";
}
