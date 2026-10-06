"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  DEMO_TENANT_ID,
  configurationIssue,
  displayApiError,
  getHealth,
  startScenario1,
  startScenario2,
  startScenario3,
} from "@/lib/api";
import type { HealthResponse } from "@/lib/types";

type ScenarioChoice = "scenario-1" | "scenario-2" | "scenario-3";

type Readiness =
  | { kind: "checking"; message: string }
  | { kind: "ready"; message: string }
  | { kind: "unavailable"; message: string };

const SCENARIOS: Record<
  ScenarioChoice,
  {
    eyebrow: string;
    title: string;
    description: string;
    demonstrates: string;
  }
> = {
  "scenario-1": {
    eyebrow: "Сценарий 1 · локальный инцидент",
    title: "Терминал потерял сетевое подключение",
    description:
      "Один локальный сбой: агент собирает Product Evidence, формирует предложение на выезд Field Service и ждёт решения человека.",
    demonstrates: "Локальная диагностика · Evidence · HITL",
  },
  "scenario-2": {
    eyebrow: "Сценарий 2 · массовый сервисный инцидент",
    title: "Несколько сигналов указывают на общую зависимость",
    description:
      "Несколько событий коррелируются в сервисный инцидент. Агент проверяет общую зависимость, формирует предложение Major Incident и ждёт решения человека.",
    demonstrates: "Корреляция · внешняя зависимость · Major Incident",
  },
  "scenario-3": {
    eyebrow: "Сценарий 3 · перепланирование по фактам",
    title: "Гипотеза о провайдере опровергается Evidence",
    description:
      "Агент сначала проверяет AcmePay, получает HEALTHY, затем меняет диагностическое направление и переходит к локальной проверке терминала.",
    demonstrates: "Опровержение гипотезы · replanning · Evidence",
  },
};

function baseReadiness(health: HealthResponse): Readiness {
  if (
    health.status === "ok" &&
    health.database_reachable &&
    health.adk_wired &&
    health.adk_session_persistence_wired &&
    health.gemini_configured
  ) {
    return {
      kind: "ready",
      message: `Product API доступен · Gemini настроен · checkpoint ${health.checkpoint}`,
    };
  }

  return {
    kind: "unavailable",
    message: health.gemini_configured
      ? "Product API доступен не полностью: проверьте runtime и базу данных."
      : "Gemini не настроен на Product API.",
  };
}

function isScenarioReady(
  scenario: ScenarioChoice,
  health: HealthResponse | null,
  readiness: Readiness,
): boolean {
  if (!health || readiness.kind !== "ready") return false;

  if (scenario === "scenario-1") {
    return Boolean(health.automatic_dispatch_wired);
  }

  if (scenario === "scenario-2") {
    return Boolean(
      health.scenario2_ingestion_wired &&
        health.scenario2_dispatch_consumer_wired &&
        health.scenario2_tools_wired &&
        health.scenario2_hitl_wired,
    );
  }

  return Boolean(
    health.scenario3_phase8c1_provider_reads_wired &&
      health.scenario3_phase8c2_native_wired,
  );
}

export function StartScenario() {
  const router = useRouter();
  const [selectedScenario, setSelectedScenario] =
    useState<ScenarioChoice>("scenario-1");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [readiness, setReadiness] = useState<Readiness>(() => {
    const issue = configurationIssue();
    return issue
      ? { kind: "unavailable", message: issue }
      : { kind: "checking", message: "Проверяем Product API…" };
  });
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    if (configurationIssue()) {
      return () => controller.abort();
    }

    void getHealth(controller.signal)
      .then((nextHealth) => {
        setHealth(nextHealth);
        setReadiness(baseReadiness(nextHealth));
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setReadiness({
          kind: "unavailable",
          message: displayApiError(error),
        });
      });

    return () => controller.abort();
  }, []);

  const scenarioReady = useMemo(
    () => isScenarioReady(selectedScenario, health, readiness),
    [health, readiness, selectedScenario],
  );

  const selected = SCENARIOS[selectedScenario];
  const readinessMessage =
    readiness.kind === "ready" && !scenarioReady
      ? "Этот сценарий пока не готов на текущем backend deployment."
      : readiness.message;

  async function handleStart() {
    if (starting || !scenarioReady) return;
    setStarting(true);
    setStartError(null);

    try {
      const state =
        selectedScenario === "scenario-2"
          ? await startScenario2()
          : selectedScenario === "scenario-3"
            ? await startScenario3()
            : await startScenario1();

      router.push(`/runs/${encodeURIComponent(state.run.run_id)}`);
    } catch (error) {
      setStartError(displayApiError(error));
      setStarting(false);
    }
  }

  return (
    <section className="launch-card" aria-labelledby="scenario-title">
      <div
        className="scenario-switcher"
        role="group"
        aria-label="Выберите демонстрационный сценарий"
      >
        {(["scenario-1", "scenario-2", "scenario-3"] as const).map(
          (scenario, index) => (
            <button
              key={scenario}
              type="button"
              data-active={selectedScenario === scenario}
              aria-pressed={selectedScenario === scenario}
              onClick={() => {
                setSelectedScenario(scenario);
                setStartError(null);
              }}
            >
              Сценарий {index + 1}
            </button>
          ),
        )}
      </div>

      <div className="launch-copy">
        <p className="eyebrow">{selected.eyebrow}</p>
        <h2 id="scenario-title">{selected.title}</h2>
        <p>{selected.description}</p>
        <p className="scenario-demonstrates">{selected.demonstrates}</p>
      </div>

      <div className="readiness-row">
        <span
          className="status-dot"
          data-state={
            readiness.kind === "ready" && !scenarioReady
              ? "unavailable"
              : readiness.kind
          }
          aria-hidden="true"
        />
        <div>
          <strong>
            {readiness.kind === "ready" && scenarioReady
              ? "Сценарий готов"
              : readiness.kind === "checking"
                ? "Проверяем backend"
                : readiness.kind === "ready"
                  ? "Сценарий недоступен"
                  : "Backend недоступен"}
          </strong>
          <span>{readinessMessage}</span>
        </div>
      </div>

      <div className="launch-meta">
        <span>Demo tenant</span>
        <code>{DEMO_TENANT_ID}</code>
      </div>

      {startError ? (
        <p className="inline-error" role="alert">
          {startError}
        </p>
      ) : null}

      <button
        className="primary-button"
        type="button"
        onClick={handleStart}
        disabled={starting || !scenarioReady}
      >
        {starting ? "Запускаем симуляцию…" : "Запустить симуляцию"}
      </button>
    </section>
  );
}
