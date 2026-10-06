"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { displayApiError, getRunState } from "@/lib/api";
import { RunConsole } from "@/components/run-console";
import { Scenario2Console } from "@/components/scenario2-console";

type RunKind = "loading" | "standard" | "scenario-2" | "error";

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

  return (
    <main className="console-shell">
      <div className="console-loading">
        <span className="spinner" aria-hidden="true" />
        <strong>Определяем сценарий запуска</strong>
        <span>{runId}</span>
      </div>
    </main>
  );
}
