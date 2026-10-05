import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

async function loadApi() {
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example.test");
  vi.stubEnv("NEXT_PUBLIC_DEMO_TENANT_ID", "TENANT-8OCT");
  return await import("../lib/api");
}

describe("browser API client contract", () => {
  it("fails closed when required public tenant configuration is missing", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example.test");
    vi.stubEnv("NEXT_PUBLIC_DEMO_TENANT_ID", "");
    const api = await import("../lib/api");

    expect(api.configurationIssue()).toBe(
      "NEXT_PUBLIC_DEMO_TENANT_ID is not configured.",
    );
  });

  it("sends configured tenant header when starting Scenario 1", async () => {
    const calls: Array<[RequestInfo | URL, RequestInit | undefined]> = [];
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        calls.push([input, init]);
        return new Response(
        JSON.stringify({
          run: {
            run_id: "RUN-1",
            tenant_id: "TENANT-8OCT",
            scenario_id: "scenario-1",
            status: "ACTIVE",
            created_at: "2026-10-05T00:00:00Z",
            updated_at: "2026-10-05T00:00:00Z",
          },
          incidents: [],
          evidence: [],
          proposals: [],
          approvals: [],
          executed_actions: [],
          work_orders: [],
          latest_event_seq: 3,
        }),
        {
          status: 201,
          headers: { "Content-Type": "application/json" },
        },
      );
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    const api = await loadApi();
    await api.startScenario1();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = calls[0]!;
    expect(url).toBe("https://api.example.test/api/v1/scenario-1/runs");
    expect(init?.method).toBe("POST");
    const headers = init?.headers as Headers;
    expect(headers.get("X-Tenant-ID")).toBe("TENANT-8OCT");
  });

  it("sends tenant and typed JSON body for Approve", async () => {
    const calls: Array<[RequestInfo | URL, RequestInit | undefined]> = [];
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        calls.push([input, init]);
        return new Response(
        JSON.stringify({
          approval: {
            approval_id: "APR-1",
            tenant_id: "TENANT-8OCT",
            run_id: "RUN-1",
            proposal_id: "PROP-1",
            decision: "APPROVED",
            decided_at: "2026-10-05T00:00:00Z",
            decided_by: "operator",
          },
          proposal: {
            proposal_id: "PROP-1",
            tenant_id: "TENANT-8OCT",
            run_id: "RUN-1",
            incident_id: "INC-1",
            device_id: "POS-1",
            diagnosis: "LOCAL_ACCESS_LINK_FAILURE",
            action_type: "FIELD_SERVICE_VISIT",
            evidence_ids: ["E-1"],
            rationale: "Evidence-backed proposal.",
            status: "EXECUTED",
            created_at: "2026-10-05T00:00:00Z",
            updated_at: "2026-10-05T00:00:01Z",
          },
          incident: {
            incident_id: "INC-1",
            tenant_id: "TENANT-8OCT",
            run_id: "RUN-1",
            site_id: "SITE-1",
            reported_device_id: "POS-1",
            symptom: "offline",
            status: "ESCALATED",
            created_at: "2026-10-05T00:00:00Z",
            updated_at: "2026-10-05T00:00:01Z",
          },
          executed_action: null,
          work_order: null,
          replayed: false,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    const api = await loadApi();
    await api.decideProposal(
      "RUN-1",
      "PROP-1",
      "approve",
      "portfolio-demo-operator",
    );

    const [url, init] = calls[0]!;
    expect(url).toBe(
      "https://api.example.test/api/v1/runs/RUN-1/proposals/PROP-1/approve",
    );
    expect(init?.method).toBe("POST");
    const headers = init?.headers as Headers;
    expect(headers.get("X-Tenant-ID")).toBe("TENANT-8OCT");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init?.body))).toEqual({
      decided_by: "portfolio-demo-operator",
    });
  });

  it("uses streaming fetch with tenant header and persisted cursor", async () => {
    const calls: Array<[RequestInfo | URL, RequestInit | undefined]> = [];
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        calls.push([input, init]);
        return new Response("", {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example.test");
    vi.stubEnv("NEXT_PUBLIC_DEMO_TENANT_ID", "TENANT-8OCT");
    const { streamRunEvents } = await import("../lib/sse");

    const controller = new AbortController();
    const onOpen = vi.fn();
    await streamRunEvents({
      runId: "RUN-1",
      afterSeq: 17,
      signal: controller.signal,
      onOpen,
      onEvent: vi.fn(),
    });

    expect(onOpen).toHaveBeenCalledOnce();
    const [url, init] = calls[0]!;
    expect(url).toBe(
      "https://api.example.test/api/v1/runs/RUN-1/events/stream?after_seq=17",
    );
    expect(init?.method).toBe("GET");
    const headers = init?.headers as Headers;
    expect(headers.get("X-Tenant-ID")).toBe("TENANT-8OCT");
    expect(headers.get("Accept")).toBe("text/event-stream");
  });
});
