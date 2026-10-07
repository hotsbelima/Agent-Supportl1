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

describe("Phase 9A final public UI", () => {
  it("keeps the landing page focused on the product rather than implementation trivia", () => {
    expect(homeSource).toContain("Автономный L1 Support Agent");
    expect(homeSource).toContain("Расследует инциденты");
    expect(homeSource).not.toContain("Next.js UI");
    expect(homeSource).not.toContain("Сохранённый источник истины");
    expect(homeSource).not.toContain("home-principles");
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

  it("exposes dynamic readiness and loading as semantic status regions", () => {
    expect(startSource).toContain('className="readiness-row" role="status" aria-live="polite"');
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

  it("keeps the public interface Russian while preserving canonical English domain terminology in GitHub", () => {
    expect(startSource).toContain("Запустить симуляцию");
    expect(standardConsole).toContain("Хронология");
    expect(scenario2Console).toContain("Крупный инцидент");
    expect(terminology).toContain("| Инцидент | Incident |");
    expect(terminology).toContain("| Наблюдение | Evidence / Observation |");
    expect(terminology).toContain("| Крупный инцидент | Major Incident |");
  });
});
