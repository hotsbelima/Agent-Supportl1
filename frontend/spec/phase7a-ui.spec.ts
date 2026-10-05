import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const startSource = readFileSync(
  new URL("../components/start-scenario.tsx", import.meta.url),
  "utf8",
);
const consoleSource = readFileSync(
  new URL("../components/run-console.tsx", import.meta.url),
  "utf8",
);
const cssSource = readFileSync(
  new URL("../app/globals.css", import.meta.url),
  "utf8",
);

describe("Phase 7A operational UI contract", () => {
  it("keeps Start simulation as a Product event trigger, not browser ADK orchestration", () => {
    expect(startSource).toContain("Start simulation");
    expect(startSource).toContain("startScenario1()");
    expect(startSource).not.toContain("/agent/invoke");
    expect(startSource).not.toContain("invokeScenario");
  });

  it("uses same-panel list to detail navigation for incidents and observations", () => {
    expect(consoleSource).toContain("<h2>Incidents</h2>");
    expect(consoleSource).toContain("<h2>Observations</h2>");
    expect(consoleSource.match(/Подробнее/g)?.length).toBeGreaterThanOrEqual(2);
    expect(consoleSource.match(/← Назад к списку/g)?.length).toBeGreaterThanOrEqual(2);
    expect(consoleSource).toContain("setSelectedIncidentId");
    expect(consoleSource).toContain("setSelectedObservationId");
  });

  it("uses native responsive vertical scrolling without custom wheel interception", () => {
    expect(cssSource).toContain("overflow-y: auto");
    expect(cssSource).toContain("overflow-x: hidden");
    expect(cssSource).toContain("-webkit-overflow-scrolling: touch");
    expect(cssSource).toContain("overscroll-behavior-y: auto");
    expect(consoleSource).not.toContain("onWheel");
    expect(consoleSource).not.toContain("addEventListener(\"wheel\"");
  });
});
