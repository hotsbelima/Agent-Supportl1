"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  DEMO_TENANT_ID,
  configurationIssue,
  displayApiError,
  getHealth,
  startScenario1,
  startScenario3,
} from "@/lib/api";
import type { HealthResponse } from "@/lib/types";

type ScenarioChoice = "scenario-1" | "scenario-3";

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
  }
> = {
  "scenario-1": {
    eyebrow: "Scenario 1 · 8 Щупалец",
    title: "Local terminal connectivity incident",
    description:
      "Start the original device-incident flow. The Product backend persists the operational signal, then dispatches the same run to the native ADK agent.",
  },
  "scenario-3": {
    eyebrow: "Scenario 3 · Evidence-driven replanning",
    title: "Payment timeout with a disproved provider hypothesis",
    description:
      "Start the replanning flow. The agent investigates AcmePay first, then can move into local device diagnostics only after Product evidence disproves the upstream-provider hypothesis.",
  },
};

function baseReadiness(health: HealthResponse): Readiness {
  if (
    health.status === "ok" &&
    health.database_reachable &&
    health.adk_wired &&
    health.adk_session_persistence_wired &&
    health.adk_resumability_wired &&
    health.gemini_configured &&
    health.automatic_dispatch_wired
  ) {
    return {
      kind: "ready",
      message: `Backend ready · Phase ${health.checkpoint} · automatic ADK dispatch`,
    };
  }

  return {
    kind: "unavailable",
    message: health.gemini_configured
      ? "Automatic ADK dispatch is not ready."
      : "Gemini is not configured on the Product backend.",
  };
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
      : { kind: "checking", message: "Checking product API…" };
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

  const scenarioReady = useMemo(() => {
    if (readiness.kind !== "ready") return false;
    if (selectedScenario === "scenario-1") return true;
    return Boolean(
      health?.scenario3_phase8c1_provider_reads_wired &&
        health?.scenario3_phase8c2_native_wired,
    );
  }, [health, readiness.kind, selectedScenario]);

  const selected = SCENARIOS[selectedScenario];
  const readinessMessage =
    selectedScenario === "scenario-3" &&
    readiness.kind === "ready" &&
    !scenarioReady
      ? "Scenario 3 provider reads or native runtime are not fully wired."
      : readiness.message;

  async function handleStart() {
    if (starting || !scenarioReady) return;
    setStarting(true);
    setStartError(null);
    try {
      const state =
        selectedScenario === "scenario-3"
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
        aria-label="Choose demo scenario"
      >
        <button
          type="button"
          data-active={selectedScenario === "scenario-1"}
          aria-pressed={selectedScenario === "scenario-1"}
          onClick={() => {
            setSelectedScenario("scenario-1");
            setStartError(null);
          }}
        >
          Scenario 1
        </button>
        <button
          type="button"
          data-active={selectedScenario === "scenario-3"}
          aria-pressed={selectedScenario === "scenario-3"}
          onClick={() => {
            setSelectedScenario("scenario-3");
            setStartError(null);
          }}
        >
          Scenario 3
        </button>
      </div>

      <div className="launch-copy">
        <p className="eyebrow">{selected.eyebrow}</p>
        <h2 id="scenario-title">{selected.title}</h2>
        <p>{selected.description}</p>
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
              ? "Product API ready"
              : readiness.kind === "checking"
                ? "Checking backend"
                : selectedScenario === "scenario-3" &&
                    readiness.kind === "ready"
                  ? "Scenario 3 unavailable"
                  : "Backend unavailable"}
          </strong>
          <span>{readinessMessage}</span>
        </div>
      </div>

      <div className="launch-meta">
        <span>Tenant</span>
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
        {starting ? "Starting simulation…" : "Start simulation"}
      </button>
    </section>
  );
}
