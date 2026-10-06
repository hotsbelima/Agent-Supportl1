import type {
  ApiErrorResponse,
  ApprovalDecisionResponse,
  HealthResponse,
  RunStateResponse,
  Scenario2ApprovalDecisionResponse,
  Scenario2IngestionStateResponse,
  Scenario2SimulatorStepResponse,
  TimelineResponse,
} from "./types";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "")
  .trim()
  .replace(/\/+$/, "");

export const DEMO_TENANT_ID =
  (process.env.NEXT_PUBLIC_DEMO_TENANT_ID ?? "").trim();

export class ApiClientError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryable: boolean,
  ) {
    super(message);
    this.name = "ApiClientError";
  }

  static async fromResponse(response: Response): Promise<ApiClientError> {
    let body: ApiErrorResponse | null = null;
    try {
      body = (await response.json()) as ApiErrorResponse;
    } catch {
      body = null;
    }
    const error = body?.error;
    return new ApiClientError(
      response.status,
      error?.code ?? "HTTP_ERROR",
      error?.message ?? "Запрос к API продукта завершился ошибкой.",
      error?.retryable ?? response.status >= 500,
    );
  }
}

export function configurationIssue(): string | null {
  if (!API_BASE_URL) return "Не настроен адрес API продукта.";
  if (!DEMO_TENANT_ID) {
    return "Не настроен демонстрационный контур интерфейса.";
  }
  return null;
}

export function apiUrl(path: string): string {
  const issue = configurationIssue();
  if (issue) {
    throw new ApiClientError(0, "FRONTEND_MISCONFIGURED", issue, false);
  }
  return `${API_BASE_URL}${path}`;
}

export function tenantHeaders(extra: HeadersInit = {}): Headers {
  const headers = new Headers(extra);
  headers.set("X-Tenant-ID", DEMO_TENANT_ID);
  return headers;
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    cache: "no-store",
    headers: tenantHeaders(init.headers),
  });
  if (!response.ok) throw await ApiClientError.fromResponse(response);
  return (await response.json()) as T;
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(apiUrl("/health"), {
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw await ApiClientError.fromResponse(response);
  return (await response.json()) as HealthResponse;
}

export function startScenario1(signal?: AbortSignal): Promise<RunStateResponse> {
  return requestJson<RunStateResponse>("/api/v1/scenario-1/runs", {
    method: "POST",
    signal,
  });
}

export function startScenario2(
  signal?: AbortSignal,
): Promise<Scenario2IngestionStateResponse> {
  return requestJson<Scenario2IngestionStateResponse>(
    "/api/v1/scenario-2/runs",
    {
      method: "POST",
      signal,
    },
  );
}

export function startScenario3(signal?: AbortSignal): Promise<RunStateResponse> {
  return requestJson<RunStateResponse>("/api/v1/scenario-3/runs", {
    method: "POST",
    signal,
  });
}

export function getRunState(
  runId: string,
  signal?: AbortSignal,
): Promise<RunStateResponse> {
  return requestJson<RunStateResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}`,
    { signal },
  );
}

export function getScenario2State(
  runId: string,
  signal?: AbortSignal,
): Promise<Scenario2IngestionStateResponse> {
  return requestJson<Scenario2IngestionStateResponse>(
    `/api/v1/scenario-2/runs/${encodeURIComponent(runId)}`,
    { signal },
  );
}

export function advanceScenario2Simulator(
  runId: string,
  signal?: AbortSignal,
): Promise<Scenario2SimulatorStepResponse> {
  return requestJson<Scenario2SimulatorStepResponse>(
    `/api/v1/scenario-2/runs/${encodeURIComponent(runId)}/simulator/next`,
    {
      method: "POST",
      signal,
    },
  );
}

export function decideScenario2Proposal(
  runId: string,
  proposalId: string,
  decision: "approve" | "reject",
  decidedBy: string,
  signal?: AbortSignal,
): Promise<Scenario2ApprovalDecisionResponse> {
  return requestJson<Scenario2ApprovalDecisionResponse>(
    `/api/v1/scenario-2/runs/${encodeURIComponent(
      runId,
    )}/proposals/${encodeURIComponent(proposalId)}/${decision}`,
    {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decided_by: decidedBy }),
    },
  );
}

export function getRunTimeline(
  runId: string,
  afterSeq = 0,
  limit = 1000,
  signal?: AbortSignal,
): Promise<TimelineResponse> {
  const params = new URLSearchParams({
    after_seq: String(afterSeq),
    limit: String(limit),
  });
  return requestJson<TimelineResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/events?${params}`,
    { signal },
  );
}

export function decideProposal(
  runId: string,
  proposalId: string,
  decision: "approve" | "reject",
  decidedBy: string,
  signal?: AbortSignal,
): Promise<ApprovalDecisionResponse> {
  return requestJson<ApprovalDecisionResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/proposals/${encodeURIComponent(
      proposalId,
    )}/${decision}`,
    {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decided_by: decidedBy }),
    },
  );
}

export function isRetryableApiFailure(error: unknown): boolean {
  if (error instanceof ApiClientError) return error.retryable;
  if (error instanceof Error && error.name === "AbortError") return false;
  return true;
}

export function displayApiError(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.code === "PUBLIC_DEMO_COOLDOWN") {
      return "Слишком много новых запусков подряд. Повторите попытку через несколько секунд.";
    }
    if (error.status === 429) {
      return `Лимит запросов к AI-провайдеру достигнут (${error.code}). Попробуйте позже.`;
    }
    if (error.code === "GEMINI_NOT_CONFIGURED") {
      return "Gemini не настроен на API продукта.";
    }
    if (error.code === "RUN_NOT_FOUND") {
      return "Запуск не найден в текущем демонстрационном контуре.";
    }
    if (error.status >= 500) {
      return `API продукта временно недоступен (${error.code}).`;
    }
    return `API продукта отклонил запрос (${error.code}).`;
  }
  if (error instanceof Error && error.name === "AbortError") {
    return "Запрос отменён.";
  }
  return "API продукта сейчас недоступен.";
}
