# Architecture

## System overview

The Autonomous L1 Incident Agent separates **business truth** from **agent
runtime state**.

```mermaid
flowchart LR
    U[Operator / Recruiter] --> F[Next.js public console]
    F -->|HTTPS| API[FastAPI Product API]
    F <-->|Persisted SSE timeline| API

    API --> APP[Product application services]
    APP --> DOMAIN[Domain rules / HITL / stale checks]
    APP --> DB[(PostgreSQL Product state)]
    APP --> OUTBOX[(Durable outbox)]

    OUTBOX --> D1[Scenario 1/3 dispatcher]
    OUTBOX --> D2[Scenario 2 dispatcher]

    D1 --> ADK[Google ADK runtimes]
    D2 --> ADK

    ADK --> GEM[Gemini]
    ADK --> TOOLS[Typed Product tool adapters]
    TOOLS --> APP

    APP --> SOURCES[Controlled demo source adapters]
    SOURCES --> CMDB[CMDB-like source]
    SOURCES --> MON[Monitoring / network source]
    SOURCES --> ITSM[ITSM / incident source]
    SOURCES --> EXT[External provider source]
    SOURCES --> KB[Knowledge source]

    APP --> HITL[Human decision boundary]
    HITL --> API

    ADK --> ADKDB[(Native ADK session persistence)]
    ADKDB --> DB
```

## Ownership boundaries

### Product owns business truth

The Product layer owns:

- runs and incidents;
- Evidence;
- action / Major Incident proposals;
- approvals and rejections;
- executed demo actions;
- work orders / Major Incidents;
- application events;
- durable dispatch state;
- stale revalidation and exactly-once rules.

The model cannot directly declare that a business action happened.

### ADK owns agent runtime continuity

Google ADK owns:

- native agent execution;
- tool-calling lifecycle;
- session continuity;
- invocation continuity;
- long-running human-decision wait/resume behavior.

The project does not implement a second generic session/runtime framework.

### Browser is a read/control surface

The frontend:

- starts persisted Product runs;
- reads Product state;
- consumes persisted event timelines through SSE;
- sends human approval/rejection;
- advances the bounded Scenario 2 simulator.

It does not orchestrate model planning.

## Write path

```mermaid
sequenceDiagram
    participant UI as Browser
    participant API as Product API
    participant DB as PostgreSQL
    participant O as Outbox worker
    participant ADK as Google ADK
    participant T as Product tools
    participant H as Human

    UI->>API: Start run / add supported demo event
    API->>DB: Persist Product state + application event + outbox
    API-->>UI: Persisted state
    O->>DB: Claim durable envelope
    O->>ADK: Invoke with persisted operational context
    ADK->>T: Read/act through typed tools
    T->>DB: Persist Evidence / proposal
    ADK-->>H: Wait for human decision
    H->>API: Approve / Reject
    API->>DB: Revalidate + commit authoritative decision
    API->>ADK: Resume native invocation
    UI->>API: Re-read authoritative state / timeline
```

## Recovery model

Recovery is based on persisted truth rather than browser memory.

- Product state survives frontend refresh/reopen.
- SSE reconnect uses persisted event sequence/cursor.
- Durable outbox allows redelivery after process failure.
- ADK sessions are persisted in the database.
- Human decisions are idempotent.
- Approval-time revalidation can mark a proposal stale instead of executing it.
- Replay cannot create duplicate actions/work orders.

## Public-demo boundary

Public demo mode is intentionally simple:

- one fixed server-side demo tenant;
- exact CORS allowlist;
- hidden internal/acceptance mutation routes;
- hidden direct Scenario 2 raw ingestion;
- simple in-process cooldown for new Gemini-backed demo runs;
- safe API errors;
- static bundle secret audit.

This is a portfolio demo boundary, not enterprise authentication/RBAC.

## Reasoning privacy

Persisted Product state and UI may contain:

- tool calls;
- safe tool results;
- Product Evidence;
- application events;
- concise model output.

Hidden chain-of-thought is not persisted or displayed.
