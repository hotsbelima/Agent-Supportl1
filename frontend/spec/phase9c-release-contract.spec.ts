import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const launcher = readFileSync(new URL("../components/start-scenario.tsx", import.meta.url), "utf8");
const runConsole = readFileSync(new URL("../components/run-console.tsx", import.meta.url), "utf8");
const scenario2Console = readFileSync(new URL("../components/scenario2-console.tsx", import.meta.url), "utf8");
const runRouter = readFileSync(new URL("../components/run-router.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
const presentation = readFileSync(new URL("../lib/presentation.ts", import.meta.url), "utf8");
const recovery = readFileSync(new URL("../lib/recovery.ts", import.meta.url), "utf8");
const nextConfig = readFileSync(new URL("../next.config.ts", import.meta.url), "utf8");

describe("Phase 9C deterministic public-demo release contract", () => {
  it("uses one same-origin browser API boundary independent of Vercel preview hostnames", () => {
    expect(api).toContain('const API_BASE_URL = "/product-api"');
    expect(nextConfig).toContain('source: "/product-api/:path*"');
  });

  it("keeps all three browser starts on persisted Product API routes", () => {
    expect(launcher).toContain("startScenario1()");
    expect(launcher).toContain("startScenario2()");
    expect(launcher).toContain("startScenario3()");
    expect(api).toContain('"/api/v1/scenario-1/runs"');
    expect(api).toContain('"/api/v1/scenario-2/runs"');
    expect(api).toContain('"/api/v1/scenario-3/runs"');
    expect(api).not.toContain("requestJson<AgentInvocationResponse>");
  });

  it("routes Scenario 2 to its specialized persisted console", () => {
    expect(runRouter).toContain('state.run.scenario_id === "scenario-2"');
    expect(runRouter).toContain("<Scenario2Console");
    expect(scenario2Console).toContain("getScenario2State");
    expect(scenario2Console).toContain("advanceScenario2Simulator");
    expect(scenario2Console).toContain("getRunTimeline");
    expect(scenario2Console).toContain("streamRunEvents");
  });

  it("creates the first Scenario 2 incident immediately, then auto-advances every 20 seconds", () => {
    expect(scenario2Console).toContain("AUTO_SIGNAL_INTERVAL_MS = 20_000");
    expect(scenario2Console).toContain("signalCount === 0");
    expect(scenario2Console).toContain("? 0");
    expect(scenario2Console).toContain("advanceScenario2Simulator(runId, controller.signal)");
    expect(scenario2Console).toContain("latestSignalAt ?? state?.run.created_at");
    expect(scenario2Console).not.toContain("Добавить следующий сигнал");
  });

  it("paces the visible timeline every 10 seconds and renders newest visible events first", () => {
    expect(presentation).toContain("TIMELINE_PLAYBACK_INTERVAL_MS = 10_000");
    expect(presentation).toContain("Math.floor(elapsedMs / TIMELINE_PLAYBACK_INTERVAL_MS) + 1");
    expect(presentation).toContain("return ordered.slice(0, visibleCount).reverse()");
    expect(runConsole).toContain("visibleTimelineEvents(events, state.run.created_at, playbackNow)");
    expect(scenario2Console).toContain("visibleTimelineEvents(");
    expect(scenario2Console).toContain("state.run.created_at");
  });

  it("keeps the portfolio UI focused on the investigation instead of internal runtime metadata", () => {
    expect(launcher).not.toContain('className="readiness-row"');
    expect(runConsole).not.toContain("8O");
    expect(scenario2Console).not.toContain("8O");
    expect(runConsole).not.toContain("Источник истины: состояние продукта в PostgreSQL");
    expect(scenario2Console).not.toContain("Источник истины: состояние продукта в PostgreSQL");
    expect(runConsole).toContain("Наблюдаемые факты");
    expect(runConsole).toContain("История событий");
    expect(runConsole).toContain("Подтверждение действий агента");
    expect(runConsole).toContain('className="run-footer-bar"');
    expect(scenario2Console).toContain('className="run-footer-bar"');
  });

  it("localizes action and diagnosis enum values in the presentation layer", () => {
    expect(presentation).toContain('LOCAL_ACCESS_LINK_FAILURE: "Сбой локального канала доступа"');
    expect(presentation).toContain('ONSITE_FIELD_VISIT: "Выезд специалиста на площадку"');
    expect(runConsole).toContain("diagnosisLabel(latestProposal.diagnosis)");
    expect(runConsole).toContain("actionTypeLabel(latestProposal.action_type)");
    expect(scenario2Console).toContain("actionTypeLabel(latestProposal.action_type)");
    expect(presentation).toContain('"Заявка на выездной сервис зарегистрирована."');
    expect(presentation).not.toContain("Это ещё не подтверждает ремонт устройства");
  });

  it("uses the correct human-decision API family per scenario type", () => {
    expect(runConsole).toContain("decideProposal(");
    expect(scenario2Console).toContain("decideScenario2Proposal(");
    expect(api).toContain("/api/v1/runs/");
    expect(api).toContain("/proposals/");
    expect(api).toContain("/api/v1/scenario-2/runs/");
  });

  it("new simulation navigates away instead of deleting old Product history", () => {
    for (const source of [runConsole, scenario2Console]) {
      expect(source).toContain('className="secondary-button compact-button" href="/"');
      expect(source).toContain("Новый запуск");
      expect(source).not.toContain("deleteRun");
      expect(source).not.toContain("/reset");
    }
  });

  it("recovers interrupted standard decisions from authoritative Product state", () => {
    expect(runConsole).toContain("decisionRecoveryStatus(");
    expect(runConsole).toContain("const recovered = await refreshState()");
    expect(recovery).toContain('proposal.status === "PENDING_APPROVAL"');
    expect(recovery).toContain('proposal.status === "REJECTED"');
    expect(recovery).toContain('proposal.status === "STALE"');
    expect(recovery).toContain('proposal.status === "EXECUTED"');
  });

  it("recovers Scenario 2 decision responses by re-reading persisted state", () => {
    expect(scenario2Console).toContain("const recovered = await refreshState()");
    expect(scenario2Console).toContain('persisted.status !== "PENDING_APPROVAL"');
    expect(scenario2Console).toContain("повтор безопасен");
  });

  it("keeps reconnect/backfill behavior based on persisted Product events", () => {
    expect(runConsole).toContain("prepareReconnect");
    expect(runConsole).toContain("mergeTimelineEvents");
    expect(scenario2Console).toContain("getRunTimeline(runId, current, 1000");
    expect(recovery).toContain("connectionStateForFailure");
    expect(recovery).toContain("reconnectDelayMs");
  });

  it("distinguishes public-demo cooldown from provider quota", () => {
    expect(api).toContain('error.code === "PUBLIC_DEMO_COOLDOWN"');
    expect(api).toContain("AI-провайдеру");
  });
});
