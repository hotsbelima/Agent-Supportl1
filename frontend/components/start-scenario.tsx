"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  DEMO_TENANT_ID,
  configurationIssue,
  displayApiError,
  getHealth,
  startScenario1,
} from "@/lib/api";

type Readiness =
  | { kind: "checking"; message: string }
  | { kind: "ready"; message: string }
  | { kind: "unavailable"; message: string };

export function StartScenario() {
  const router = useRouter();
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
      .then((health) => {
        if (health.status === "ok" && health.database_reachable) {
          setReadiness({
            kind: "ready",
            message: `Backend ready · Phase ${health.checkpoint}`,
          });
          return;
        }
        setReadiness({
          kind: "unavailable",
          message: "Backend health check is not ready.",
        });
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

  async function handleStart() {
    if (starting || readiness.kind !== "ready") return;
    setStarting(true);
    setStartError(null);
    try {
      const state = await startScenario1();
      router.push(`/runs/${encodeURIComponent(state.run.run_id)}`);
    } catch (error) {
      setStartError(displayApiError(error));
      setStarting(false);
    }
  }

  return (
    <section className="launch-card" aria-labelledby="scenario-title">
      <div className="launch-copy">
        <p className="eyebrow">Scenario 1 · 8 Щупалец</p>
        <h2 id="scenario-title">Local terminal connectivity incident</h2>
        <p>
          Start the simulated environment. The first operational signal is
          persisted by the Product backend, then the backend automatically
          dispatches the same run to the native ADK agent.
        </p>
      </div>

      <div className="readiness-row">
        <span
          className="status-dot"
          data-state={readiness.kind}
          aria-hidden="true"
        />
        <div>
          <strong>
            {readiness.kind === "ready"
              ? "Product API ready"
              : readiness.kind === "checking"
                ? "Checking backend"
                : "Backend unavailable"}
          </strong>
          <span>{readiness.message}</span>
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
        disabled={starting || readiness.kind !== "ready"}
      >
        {starting ? "Starting simulation…" : "Start simulation"}
      </button>
    </section>
  );
}
