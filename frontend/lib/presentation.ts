import type {
  ApplicationEventView,
  ConnectionState,
  EvidenceView,
  JsonValue,
  ProposalView,
} from "./types";

export const FIELD_SERVICE_OUTCOME_NOTE =
  "Выезд Field Service зарегистрирован. Это ещё не подтверждает ремонт устройства.";

export const STALE_PROPOSAL_NOTE =
  "Решение человека сохранено, но свежие авторитетные данные больше не разрешают выполнение. Действие Field Service не создавалось.";

function stringValue(
  payload: Record<string, JsonValue>,
  key: string,
): string | null {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value : null;
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
      return "Product-действие зарегистрировано";
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
