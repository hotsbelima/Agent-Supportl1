import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const launcher = readFileSync(new URL("../components/start-scenario.tsx", import.meta.url), "utf8");
const runConsole = readFileSync(new URL("../components/run-console.tsx", import.meta.url), "utf8");
const scenario2Console = readFileSync(new URL("../components/scenario2-console.tsx", import.meta.url), "utf8");
const runRouter = readFileSync(new URL("../components/run-router.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
const recovery = readFileSync(new URL("../lib/recovery.ts", import.meta.url), "utf8");

describe("Phase 9C deterministic public-demo release contract", () => {
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

  it("auto-advances Scenario 2 every 20 seconds from persisted progress", () => {
    expect(scenario2Console).toContain("AUTO_SIGNAL_INTERVAL_MS = 20_000");
    expect(scenario2Console).toContain("advanceScenario2Simulator(runId, controller.signal)");
    expect(scenario2Console).toContain("latestSignalAt ?? state?.run.created_at");
    expect(scenario2Console).not.toContain("Добавить следующий сигнал");
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
