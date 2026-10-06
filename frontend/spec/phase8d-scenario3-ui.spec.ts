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

describe("Phase 8D Scenario 3 UI exposure", () => {
  it("offers Scenario 3 through the Product start API without browser agent orchestration", () => {
    expect(startSource).toContain("Scenario 3");
    expect(startSource).toContain("startScenario3()");
    expect(startSource).toContain("scenario3_phase8c1_provider_reads_wired");
    expect(startSource).toContain("scenario3_phase8c2_native_wired");
    expect(startSource).not.toContain("/agent/invoke");
    expect(startSource).not.toContain("invokeScenario");
  });

  it("keeps Scenario 1 as the default launch while allowing Scenario 3 selection", () => {
    expect(startSource).toContain(
      'useState<ScenarioChoice>("scenario-1")',
    );
    expect(startSource).toContain('setSelectedScenario("scenario-3")');
    expect(startSource).toContain('aria-pressed={selectedScenario === "scenario-3"}');
  });

  it("reuses one persisted run console and derives scenario identity from Product state", () => {
    expect(consoleSource).toContain("state?.run.scenario_id");
    expect(consoleSource).toContain("{scenarioLabel} operational console");
    expect(consoleSource).toContain("{state.run.scenario_id}");
    expect(consoleSource).not.toContain("Scenario 1 operational console");
    expect(consoleSource).toContain("Back to scenarios");
  });
});
