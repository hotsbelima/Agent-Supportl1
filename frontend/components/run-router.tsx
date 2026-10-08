"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { displayApiError, getRunState, sendRunHeartbeat } from "@/lib/api";
import { RunConsole } from "@/components/run-console";
import { Scenario2Console } from "@/components/scenario2-console";

type RunKind = "loading" | "standard" | "scenario-2" | "abandoned" | "error";

export function RunRouter({ runId }: { runId: string }) {
  const [kind, setKind] = useState<RunKind>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    void getRunState(runId, controller.signal)
      .then((state) => {
        setKind(state.run.scenario_id === "scenario-2" ? "scenario-2" : "standard");
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(displayApiError(reason));
        setKind("error");
      });

    return () => controller.abort();
  }, [runId]);

  useEffect(() => {
    if (kind !== "standard" && kind !== "scenario-2") return;

    const controller = new AbortController();
    let stopped = false;
    let inFlight = false;
    const heartbeat = async () => {
      if (stopped || inFlight) return;
      inFlight = true;
      try {
        const result = await sendRunHeartbeat(runId, controller.signal);
        if (!stopped && !result.active) setKind("abandoned");
      } catch {
        // A transient network failure gets another chance on the next tick.
      } finally {
        inFlight = false;
      }
    };

    void heartbeat();
    const timerId = window.setInterval(() => void heartbeat(), 20_000);
    return () => {
      stopped = true;
      controller.abort();
      window.clearInterval(timerId);
    };
  }, [kind, runId]);

  if (kind === "scenario-2") {
    return <Scenario2Console key={runId} runId={runId} />;
  }

  if (kind === "standard") {
    return <RunConsole key={runId} runId={runId} />;
  }

  if (kind === "error") {
    return (
      <main className="console-shell">
        <div className="fatal-card">
          <p className="eyebrow">Запуск недоступен</p>
          <h1>Не удалось определить сценарий</h1>
          <p>{error ?? "API продукта не вернул состояние запуска."}</p>
          <Link className="secondary-button" href="/">
            К выбору сценариев
          </Link>
        </div>
      </main>
    );
  }

  if (kind === "abandoned") {
    return (
      <main className="console-shell">
        <div className="fatal-card">
          <p className="eyebrow">Запуск остановлен</p>
          <h1>Сценарий больше не обрабатывается</h1>
          <p>
            Страница не отправляла heartbeat 90 секунд. История запуска сохранена;
            чтобы продолжить, создайте новый запуск.
          </p>
          <Link className="secondary-button" href="/">
            К выбору сценариев
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="console-shell">
      <div className="console-loading" role="status" aria-live="polite">
        <span className="spinner" aria-hidden="true" />
        <strong>Определяем сценарий запуска</strong>
        <span>{runId}</span>
      </div>
    </main>
  );
}
