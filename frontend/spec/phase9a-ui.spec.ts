import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const homeSource = readFileSync(
  new URL("../app/page.tsx", import.meta.url),
  "utf8",
);
const startSource = readFileSync(
  new URL("../components/start-scenario.tsx", import.meta.url),
  "utf8",
);
const standardConsole = readFileSync(
  new URL("../components/run-console.tsx", import.meta.url),
  "utf8",
);
const scenario2Console = readFileSync(
  new URL("../components/scenario2-console.tsx", import.meta.url),
  "utf8",
);
const runRouter = readFileSync(
  new URL("../components/run-router.tsx", import.meta.url),
  "utf8",
);
const themeToggle = readFileSync(
  new URL("../components/theme-toggle.tsx", import.meta.url),
  "utf8",
);
const cssSource = readFileSync(
  new URL("../app/globals.css", import.meta.url),
  "utf8",
);
const terminology = readFileSync(
  new URL("../../docs/phase9a_ui_terminology.md", import.meta.url),
  "utf8",
);
const apiSource = readFileSync(
  new URL("../lib/api.ts", import.meta.url),
  "utf8",
);
const presentationSource = readFileSync(
  new URL("../lib/presentation.ts", import.meta.url),
  "utf8",
);

describe("Phase 9A final public UI", () => {
  it("keeps the landing page focused on the product rather than implementation trivia", () => {
    expect(homeSource).toContain("Автономный L1 Support Agent");
    expect(homeSource).toContain("Расследует инциденты");
    expect(homeSource).not.toContain("Next.js UI");
    expect(homeSource).not.toContain("Сохранённый источник истины");
    expect(homeSource).not.toContain("home-principles");
    expect(homeSource).not.toContain("Публичное демо операционного AI");
    expect(homeSource).not.toContain("8 Щупалец · IT-операции");
    expect(startSource).not.toContain("scenario-demonstrates");
    expect(startSource).not.toContain("Демо-контур");
    expect(startSource).not.toContain("DEMO_TENANT_ID");
  });

  it("exposes all three persisted Product scenarios without browser agent orchestration", () => {
    expect(startSource).toContain('"scenario-1", "scenario-2", "scenario-3"');
    expect(startSource).toContain("startScenario1()");
    expect(startSource).toContain("startScenario2()");
    expect(startSource).toContain("startScenario3()");
    expect(startSource).not.toContain("/agent/invoke");
    expect(startSource).not.toContain("invokeScenario");
  });

  it("routes Scenario 2 to its real Product-state console", () => {
    expect(runRouter).toContain('state.run.scenario_id === "scenario-2"');
    expect(runRouter).toContain("<Scenario2Console");
    expect(scenario2Console).toContain("getScenario2State");
    expect(scenario2Console).toContain("advanceScenario2Simulator");
    expect(scenario2Console).toContain("decideScenario2Proposal");
    expect(scenario2Console).toContain("streamRunEvents");
    expect(scenario2Console).not.toContain("/agent/invoke");
  });

  it("keeps incidents as same-panel list-to-detail navigation", () => {
    expect(standardConsole).toContain("<h2>Инциденты</h2>");
    expect(standardConsole).toContain("setSelectedIncidentId");
    expect(standardConsole).toContain("← Назад к списку");
    expect(scenario2Console).toContain("<h2>Инциденты</h2>");
    expect(scenario2Console).toContain("setSelectedIncidentId");
    expect(scenario2Console).toContain("← Назад к списку");
  });

  it("bounds central panels and gives them independent vertical scrolling", () => {
    expect(cssSource).toContain("height: clamp(560px, calc(100dvh - 255px), 780px)");
    expect(cssSource).toContain("grid-template-rows: repeat(2, minmax(0, 1fr))");
    expect(cssSource).toContain("overflow-y: auto");
    expect(cssSource).toContain("overscroll-behavior: contain");
    expect(standardConsole).not.toContain("onWheel");
    expect(scenario2Console).not.toContain("onWheel");
  });

  it("keeps mobile panels compact in the investigation-first order", () => {
    expect(cssSource).toContain("height: min(28.75vh, 263px)");
    expect(cssSource).toContain(".incident-panel { order: 1; }");
    expect(cssSource).toContain(".investigation-panel { order: 2; }");
    expect(cssSource).toContain(".decision-panel { order: 3; }");
    expect(cssSource).toContain(".result-panel { order: 4; }");
    expect(cssSource).toContain(".observation-panel { order: 5; }");
    expect(cssSource).toContain(".timeline-panel { order: 6; }");
    expect(standardConsole).toContain("investigation-panel");
    expect(scenario2Console).toContain("investigation-panel");
  });

  it("keeps dark as default and light as an explicit persistent option", () => {
    expect(cssSource).toContain(":root {");
    expect(cssSource).toContain("color-scheme: dark");
    expect(cssSource).toContain(':root[data-theme="light"]');
    expect(cssSource).toContain(':root[data-theme="light"] .run-header');
    expect(cssSource).toContain(':root[data-theme="light"] .facts-grid dd');
    expect(themeToggle).toContain("useSyncExternalStore");
    expect(themeToggle).toContain('=== "light" ? "light" : "dark"');
    expect(themeToggle).toContain("window.localStorage.setItem");
  });

  it("provides a new-simulation path without destructive reset", () => {
    expect(standardConsole).toContain("Новый запуск");
    expect(scenario2Console).toContain("Новый запуск");
    expect(standardConsole).not.toContain("delete");
    expect(scenario2Console).not.toContain("delete");
  });

  it("keeps readiness gating in logic while removing launcher status chrome", () => {
    expect(startSource).not.toContain('className="readiness-row"');
    expect(startSource).toContain("getHealth(controller.signal)");
    expect(startSource).toContain("disabled={starting || !scenarioReady}");
    expect(standardConsole).toContain('className="console-loading" role="status" aria-live="polite"');
    expect(scenario2Console).toContain('className="console-loading" role="status" aria-live="polite"');
  });

  it("does not leak retained English UI copy in recovery and not-found states", () => {
    expect(standardConsole).not.toContain("Retrying persisted run state");
    expect(apiSource).not.toContain("demo tenant");
    expect(standardConsole).not.toContain("Product API");
    expect(scenario2Console).not.toContain("Product API");
    expect(startSource).not.toContain("Product API");
  });

  it("reveals Scenario 1 proposal at its creation event and keeps results authoritative", () => {
    expect(standardConsole).toContain("const visibleProposals = state?.proposals ?? [];");
    expect(standardConsole).toContain("shouldRevealProposalPanel(");
    expect(standardConsole).toContain("showProposalPanel ? (");
    expect(scenario2Console).toContain(
      "const visibleProposals = state.major_incident_proposals;",
    );
    expect(scenario2Console).not.toContain("playback.proposalIds.has");
    expect(standardConsole).toContain("state?.work_orders ?? []");
    expect(standardConsole).toContain("state?.executed_actions ?? []");
    expect(scenario2Console).toContain(
      "state.major_incident_executions.length > 0",
    );
  });

  it("shows real in-flight tools, waits for native HITL, and uses 3.5 second playback", () => {
    expect(presentationSource).toContain(
      "export const TIMELINE_PLAYBACK_INTERVAL_MS = 3_500",
    );
    expect(presentationSource).toContain("native_hitl_paused");
    expect(presentationSource).toContain("Агент выполняет:");
    expect(presentationSource).toContain("Ожидаем результат проверки.");
    expect(standardConsole).toContain("nativeHitlReady(events");
    expect(scenario2Console).toContain("nativeHitlReady(events");
    expect(standardConsole).toContain(
      'latestProposal.status === "PENDING_APPROVAL" && latestProposalHitlReady',
    );
    expect(scenario2Console).toContain(
      'latestProposal.status === "PENDING_APPROVAL" && latestProposalHitlReady',
    );
  });

  it("localizes ordinary user-facing service text while keeping raw payloads in details", () => {
    expect(presentationSource).toContain(
      '"Physical access path inspection": "Проверка физического пути подключения"',
    );
    expect(presentationSource).toContain('AcmePay: "CloudPayments"');
    expect(presentationSource).toContain(
      "Агент проверил, зарегистрирован ли уже крупный инцидент по этой проблеме",
    );
    expect(presentationSource).toContain(
      "Активного крупного инцидента по этой зависимости пока нет.",
    );
    expect(standardConsole).toContain("userFacingTextLabel(fact)");
    expect(scenario2Console).toContain("userFacingTextLabel(fact)");
    expect(standardConsole).toContain("<summary>Детали</summary>");
    expect(scenario2Console).toContain("<summary>Детали</summary>");
  });

  it("keeps the public interface Russian while preserving canonical English domain terminology in GitHub", () => {
    expect(startSource).toContain("Запустить симуляцию");
    expect(standardConsole).toContain("Ход расследования");
    expect(standardConsole).toContain("Технический журнал");
    expect(scenario2Console).toContain("Крупный инцидент");
    expect(terminology).toContain("| Инцидент | Incident |");
    expect(terminology).toContain("| Наблюдение | Evidence / Observation |");
    expect(terminology).toContain("| Крупный инцидент | Major Incident |");
  });
});
