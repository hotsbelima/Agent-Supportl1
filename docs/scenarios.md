# Demo Scenarios

The three scenarios are designed to demonstrate different agent behaviors while
keeping Product ownership and HITL rules consistent.

## Comparison

| Scenario | What happens | What the agent demonstrates | Human-controlled outcome |
| --- | --- | --- | --- |
| 1 — Local device incident | One terminal/device is unreachable | Local diagnosis using CMDB, monitoring, diagnostics and KB Evidence | Field Service proposal |
| 2 — Multi-event service incident | Multiple signals point to one service/dependency problem | Correlation, provider/service investigation and Major Incident reasoning | Major Incident proposal |
| 3 — Evidence-driven replanning | Initial provider hypothesis is disproved | Hypothesis revision and switch from provider domain to local diagnostics | Field Service proposal |

## Scenario 1 — local access-link failure

```mermaid
flowchart TD
    A[Incident created] --> B[Persist Product run/event]
    B --> C[ADK invocation]
    C --> D[Read device / CMDB]
    D --> E[Read site and access-link health]
    E --> F[Collect approved Evidence]
    F --> G[Diagnose local access-link failure]
    G --> H[Propose Field Service visit]
    H --> I{Human decision}
    I -->|Approve + truth still current| J[Exactly-once demo action + work order]
    I -->|Reject| K[No execution]
    I -->|Approve but truth changed| L[Proposal becomes STALE]
```

This scenario demonstrates that the model may investigate and propose, but
Product code owns validation and execution.

## Scenario 2 — multi-event / Major Incident

```mermaid
flowchart TD
    A[Multiple operational signals] --> B[Persist signals and correlation state]
    B --> C[ADK investigation]
    C --> D[Read local service health]
    D --> E[Read dependency mapping/status]
    E --> F[Search existing Major Incidents]
    F --> G[Persist Evidence]
    G --> H[Propose Major Incident]
    H --> I{Human decision}
    I -->|Approve| J[Create demo Major Incident]
    I -->|Reject| K[No side effect]
```

The public browser advances a finite deterministic signal sequence. Raw signal
injection is not exposed in public-demo mode.

## Scenario 3 — replanning after disconfirmation

```mermaid
flowchart TD
    A[Incident suggests provider problem] --> B[Map service dependency]
    B --> C[Read AcmePay status]
    C --> D[Provider reports HEALTHY]
    D --> E[Disconfirm provider hypothesis]
    E --> F[Switch to local diagnostic domain]
    F --> G[Read CMDB/site/access-link/KB]
    G --> H[Persist local Evidence]
    H --> I[Propose Field Service visit]
    I --> J{Human decision}
    J -->|Approve| K[Exactly-once demo action]
    J -->|Reject| L[No execution]
```

The important behavior is not merely using more tools. The agent changes its
investigation path because new Evidence contradicts its first hypothesis.

## What is mocked in the portfolio demo

The repository uses controlled source adapters rather than live customer
systems for:

- monitoring/network health;
- CMDB;
- ITSM incident data;
- knowledge articles;
- external provider health;
- Field Service / Major Incident side effects.

The architecture is built so those sources are behind typed Product
boundaries. The demo does not pretend to execute changes in real customer
infrastructure.

## What is real

The following are real project behavior:

- Google ADK runtime integration;
- Gemini tool calling;
- PostgreSQL Product persistence;
- native ADK session persistence;
- durable dispatch/outbox;
- Evidence persistence;
- HITL pause/resume;
- stale/idempotency/exactly-once rules;
- SSE timeline/recovery;
- three-scenario browser UI;
- deterministic release gate.
