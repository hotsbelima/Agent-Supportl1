# Autonomous L1 Incident Agent
## Canonical cumulative handoff v7.2 — Phase 8C2 DONE/PASS; Phase 8D NEXT

**Date:** 6 October 2026  
**Project:** Autonomous L1 Incident Agent  
**Current development stop point:** **Phase 8C2 = DONE / PASS; Phase 8D = NEXT**  
**Last live-validated code baseline:** `2f8dae61c06afd0f134c58e90aba0591a013a31e`  
**Latest deterministic Phase 8 implementation checkpoint:** `9d9d6f2a44b709c6d443e9608e4d3e026ccb0470`

---

# 1. Canonical baseline

Repository:

`hotsbelima/Agent-Supportl1`

Last fully implemented and live-validated code baseline:

`2f8dae61c06afd0f134c58e90aba0591a013a31e`

Final Phase 7 development branch:

`phase-7d-scenario2-tools-hitl`

Final deterministic GitHub Actions run:

`37399813681` — SUCCESS

Managed Product API used for Phase 7E:

`https://p01--product-api--yxz5y8myjdln.code.run/`

Alembic head:

`20261006_0006`

Important:

> Phase 8A/8B are design checkpoints. Phase 8C1 and Phase 8C2 are now implemented and deterministically verified. No managed/live Phase 8 acceptance has occurred yet, so the last live-validated runtime baseline remains the final Phase 7 baseline above.

---

# 2. Handoff/source priority from this point

When sources conflict, use this order:

1. **this cumulative handoff v7.2**
2. `docs/phase8c2_implementation_notes.md`
3. `docs/phase8c1_implementation_notes.md`
4. `Phase_8B_Contract_Tool_Gap_Analysis_and_Implementation_Plan_REVIEWED.md`
5. `Phase_8A_Scenario_3_Specification_REVIEWED.md`
6. cumulative handoff v7.1 / v7.0 / v6.9 for historical detail
7. repository code at `9d9d6f2a44b709c6d443e9608e4d3e026ccb0470`
8. Phase 7 implementation notes/specs for historical detail

The reviewed Phase 8B document supersedes the earlier non-reviewed Phase 8B draft.

Do not restore decisions that were explicitly removed during 8B review.

---

# 3. Roadmap status

- Phase 0 — DONE
- Phase 1 — DONE
- Phase 2 — DONE
- Phase 3 — DONE / PASS
- Phase 4 — DONE / PASS
- Phase 5 — DONE / PASS
- Phase 6 — DONE / PASS
- Phase 7A — DONE / PASS
- Phase 7B — DONE / PASS
- Phase 7C — DONE / PASS
- Phase 7D — DONE / PASS
- Phase 7E — DONE / PASS
- **Phase 7 — DONE / PASS**
- **Phase 8A — DONE / DESIGN PASS**
- **Phase 8B — DONE / REVIEWED DESIGN PASS**
- **Phase 8C1 — DONE / PASS**
- **Phase 8C2 — DONE / PASS**
- **Phase 8D — NEXT**
- Phase 8E — PLANNED
- Phase 9 — PLANNED

Phase 9 still owns final polish/hardening and the previously deferred light/white UI debt at the latest.

---

# 4. Phase 8 goal

Canonical roadmap wording:

> **Scenario 3: disconfirmed hypothesis → replanning → new tool sequence**

Phase 8 exists to prove that the agent can:

1. form a reasonable working hypothesis;
2. test it using Product tools;
3. receive authoritative evidence that disproves it;
4. change diagnostic domain;
5. gather a different class of evidence;
6. reach an independently supported conclusion;
7. preserve normal Product guardrails and native ADK HITL.

The target is **observable evidence-driven replanning**, not a pre-programmed workflow.

---

# 5. Canonical Scenario 3 fixed in Phase 8A

Canonical story:

> **Single-terminal payment timeout → upstream provider hypothesis investigated → AcmePay proven HEALTHY → agent changes diagnostic domain → local access-link failure independently proven → existing Field Service proposal/HITL/execution path.**

Scenario ID:

`scenario-3`

Site:

`SITE-KZN-017`

Affected terminal:

`POS-KZN17-02`

Healthy peer:

`POS-KZN17-01`

Scenario 3 device Incident:

`INC-S3-KZN-001`

Business service:

`payment_gateway`

Symptom key:

`payment_gateway_timeout`

External dependency:

`DEP-ACMEPAY-PAYMENTS`

External dependency name:

`AcmePay`

Canonical provider truth:

`HEALTHY`

Canonical local physical topology:

- attachment `ATT-KZN17-POS02`
- switch `SW-KZN17-01`
- port `Gi1/0/18`

Canonical access-link truth:

`OperationalState.DOWN`

---

# 6. Initial hypothesis and disconfirmation

Initial reasonable working hypothesis:

> the observed payment timeout may be caused by the upstream payment provider.

The agent must establish:

1. `payment_gateway` depends on AcmePay;
2. AcmePay current authoritative status is `HEALTHY`.

The relevant Product Evidence classes already exist:

- `SERVICE_DEPENDENCY_MAPPING`
- `EXTERNAL_DEPENDENCY_STATUS`

A failed tool call, missing data, timeout or retry exhaustion does **not** count as disconfirming evidence.

`AcmePay = HEALTHY` disproves the provider-outage hypothesis.

It does **not** by itself prove the local access-link root cause.

The local diagnosis must be independently supported by local Product Evidence.

---

# 7. Canonical local diagnosis after replanning

Phase 8 reuses the existing Scenario 1 Field Service path.

Existing mandatory local Evidence classes remain:

1. `CMDB_SNAPSHOT`
2. `SITE_HEALTH`
3. `ACCESS_LINK_DIAGNOSTIC`
4. approved `KB_ARTICLE`

Canonical diagnosis:

`LOCAL_ACCESS_LINK_FAILURE`

Canonical action:

`ONSITE_FIELD_VISIT`

The existing access-link validator already requires:

- switch reachable;
- admin state `UP`;
- operational state `DOWN`;
- port security `NORMAL`;
- configuration `EXPECTED`.

No Scenario 3-specific replacement validator is needed.

---

# 8. Existing Product entities reused

Phase 8B confirmed that Scenario 3 can use existing persisted Product entities:

- `Run`
- `Incident`
- `Evidence`
- `ActionProposal`
- `Approval`
- `ExecutedAction`
- `FieldServiceWorkOrder`
- Product application events
- Product outbox

No new Scenario 3 business table is currently justified.

Expected Alembic result after implementation:

`20261006_0006` remains head and `alembic check` stays clean unless implementation uncovers a real schema gap.

---

# 9. Existing Scenario 1 services reused

Repository inspection confirmed that the following Product services are not hard-bound to `scenario-1`:

- `Scenario1ReadToolService`
- `FieldVisitProposalService`
- `FieldVisitApprovalService`
- `RunStateService`
- `SqlAlchemyRunStateQuery`

They validate Product Run / Incident / Evidence state instead of requiring a specific scenario ID.

Therefore Scenario 3 should reuse them rather than clone them.

---

# 10. Scenario 2 code that must remain stable

The existing `Scenario2ReadToolService` is intentionally Scenario 2-specific.

It requires:

`run.scenario_id == "scenario-2"`

and derives known service context from Scenario 2 `OperationalSignal` persistence.

Phase 8B explicitly decided:

> **Do not refactor or loosen the live-validated Scenario 2 read service for Scenario 3.**

Scenario 3 gets a narrow provider-read application service using the existing provider-neutral contracts/source ports/Evidence types.

This reduces Phase 7 regression risk.

---

# 11. Final Scenario 3 model-visible tool surface

Canonical Scenario 3 agent surface:

## Provider domain

1. `get_service_dependencies`
2. `get_external_dependency_status`

## Local/device domain

3. `get_device`
4. `get_site_health`
5. `run_diagnostic`
6. `search_kb`

## Product proposal

7. `propose_field_visit`

## Native HITL

8. `await_human_decision`

Do not expose in Scenario 3:

- `search_incidents`
- `get_local_service_health`
- `search_major_incidents`
- `propose_major_incident`

`search_incidents` was deliberately removed during Phase 8B review because it is optional for Field Service, adds no Scenario 3 acceptance value and the existing fixture would return Scenario 1 incident `INC-1042`.

---

# 12. Replanning must not become Product workflow logic

Forbidden implementation:

```python
if provider_status == "HEALTHY":
    run_local_diagnostics()
```

Product owns:

- facts;
- Evidence;
- business validation;
- side-effect guardrails;
- approvals/execution.

ADK/model owns diagnostic tool selection and plan change.

Therefore:

> Product must not perform the replanning on behalf of Gemini.

---

# 13. Important Phase 8B correction: no artificial provider-health proposal rule

An earlier 8B draft proposed making:

`EXTERNAL_DEPENDENCY_STATUS = HEALTHY`

a mandatory Product prerequisite for `propose_field_visit`.

That decision was removed during review.

Reason:

- it is not a real Field Service business invariant;
- a local physical failure can coexist with a degraded provider;
- it would turn a demo acceptance property into permanent Product business logic;
- it still would not prove that the model genuinely replanned.

Canonical rule now:

> Replanning is proved by the observable investigation trace, not by a Scenario 3-specific proposal validator.

`FieldVisitProposalService` remains governed by the existing four local Evidence classes.

---

# 14. How replanning is proved

No chain-of-thought is required or persisted.

Use:

- Product Evidence;
- Product event order;
- native ADK tool-call history.

Canonical acceptance trace:

```text
provider-domain investigation
        ↓
SERVICE_DEPENDENCY_MAPPING
        ↓
EXTERNAL_DEPENDENCY_STATUS = HEALTHY
        ↓
initial provider hypothesis disconfirmed
        ↓
local/device diagnostic activity
        ↓
CMDB / SITE_HEALTH / ACCESS_LINK_DIAGNOSTIC / KB
        ↓
Field Service proposal
```

For the canonical Scenario 3 PASS, local/device diagnostic investigation must occur after provider disconfirmation.

A correct final diagnosis without this observable change of diagnostic domain is **not** sufficient for Phase 8 PASS.

---

# 15. Bootstrap decision

Scenario 3 uses the existing device-Incident Product start transaction pattern.

`Scenario1RunStartService` already accepts a bootstrap-provided `scenario_id`.

Do not create a separate full Scenario 3 lifecycle implementation.

Minimal planned change:

extend the historical bootstrap/safe signal contract with optional:

```text
service_key
symptom_key
```

Scenario 1 leaves them unset.

Scenario 3 sets:

```text
service_key = payment_gateway
symptom_key = payment_gateway_timeout
```

The initial Product signal must still not expose:

- AcmePay status;
- dependency root cause;
- attachment/switch/port;
- final diagnosis;
- action recommendation;
- a precomputed replan flag.

---

# 16. Dispatch decision

Scenario 3 reuses the existing generic device-Incident topic:

`AGENT_DISPATCH_TOPIC = "agent.dispatch.operational-event"`

Do **not** add a dedicated Scenario 3 outbox topic.

Scenario 1 and Scenario 3 share the same device-Incident event shape.

Scenario 2 keeps its separate operational-signal topic because its Product fact model is different.

---

# 17. Worker decision

Do not create a third durable worker.

The existing Scenario 1/device-Incident worker mechanics should be minimally generalized so runtime selection uses persisted:

`Run.scenario_id`

Conceptually:

```text
scenario-1 -> Scenario 1 runtime
scenario-3 -> Scenario 3 runtime
```

The worker continues to own only:

- durable claim;
- lease;
- Product state reload;
- native invocation delivery;
- retry/reschedule;
- delivered marking.

It does not choose hypotheses or tool sequence.

---

# 18. Scenario 3 provider-read service

Add a narrow Scenario 3 provider application service.

Do not route Scenario 3 through `Scenario2ReadToolService`.

Required methods:

- service dependency lookup;
- external dependency status lookup.

Context safety:

## Service lookup

`service_key` must match the service context persisted in the same Scenario 3 Product Run's initial `EXTERNAL_SIGNAL`.

## Dependency status lookup

`dependency_id` must first have been established by same-run `SERVICE_DEPENDENCY_MAPPING` Evidence.

This prevents arbitrary provider/entity enumeration by the model.

---

# 19. Provider source adapter

Scenario 3 source truth:

```text
payment_gateway
    -> DEP-ACMEPAY-PAYMENTS
    -> AcmePay
    -> EXTERNAL_PROVIDER

DEP-ACMEPAY-PAYMENTS
    -> HEALTHY
```

Implement using existing ports:

- `ServiceDependencyPort`
- `ExternalDependencyStatusPort`

The adapter returns source observations only.

It must never return a precomputed conclusion such as:

> "provider is healthy, diagnose the terminal."

---

# 20. Local source reuse

Scenario 3 may reuse existing:

`Scenario1FixtureSources`

for:

- CMDB;
- site health;
- access-link diagnostics;
- KB.

The canonical physical IDs already match Scenario 1's world.

The fixture's per-run access-link override can also support deterministic stale tests.

No duplicate local fixture implementation is currently needed.

---

# 21. Native ADK composition

Scenario 3 needs:

- a dedicated `LlmAgent` definition;
- a Scenario 3 tool wrapper composition;
- the same persistent ADK Session model.

It does **not** need:

- a new app/session namespace;
- a new conversation store;
- another Product-owned runtime state machine.

Canonical session ownership remains:

```text
ADK app_name   = autonomous-l1-incident-agent
ADK user_id    = Product tenant_id
ADK session_id = Product run_id
```

---

# 22. Runtime decision

Do not copy `Scenario1AgentRuntime`.

Generalize the existing device-Incident runtime minimally so scenario-specific construction is injected/configured.

Scenario 1 compatibility must remain intact.

Scenario 3 uses the same runtime mechanics with:

- Scenario 3 root agent;
- Scenario 3 envelope identity.

Still only one generic device-Incident runtime mechanism.

---

# 23. Required native HITL hardening

Phase 8 should bring the Scenario 1/3 device-Incident runtime up to the safety invariant already used in Phase 7D.

A valid native:

`await_human_decision(PROPOSAL-X)`

pause is accepted only if the same invocation previously received a successful:

`propose_field_visit`

response for exactly `PROPOSAL-X` with:

`PENDING_APPROVAL`

Also:

> a Product proposal created without a valid native wait correlation must not be considered safely delivered as a complete HITL point.

Scenario 1 regression must remain PASS after this hardening.

---

# 24. Human decision routing

Existing Field Service endpoints remain:

```text
POST /api/v1/runs/{run_id}/proposals/{proposal_id}/approve
POST /api/v1/runs/{run_id}/proposals/{proposal_id}/reject
```

Do not add Scenario 3 duplicate decision endpoints.

After Product decision commits, choose the correct native runtime from persisted:

`Run.scenario_id`

Conceptually:

```text
scenario-1 -> Scenario 1 runtime
scenario-3 -> Scenario 3 runtime
```

If native resume fails after Product commit:

- Product truth stays committed;
- response remains deferred/retryable;
- replaying the same decision is the reconciliation path.

---

# 25. Stale path

Reuse existing Field Service stale semantics.

Before human Approve, source truth changes:

```text
OperationalState.DOWN -> OperationalState.UP
```

Approve must revalidate and produce:

- Approval persisted;
- proposal `STALE`;
- no `ExecutedAction`;
- no `FieldServiceWorkOrder`;
- native invocation resumes with committed Product decision.

Do not create a new Scenario 3 stale entity/model.

---

# 26. API changes planned

Add:

```text
POST /api/v1/scenario-3/runs
```

Reuse:

```text
GET /api/v1/runs/{run_id}
GET /api/v1/runs/{run_id}/events
GET /api/v1/runs/{run_id}/events/stream

POST /api/v1/runs/{run_id}/proposals/{proposal_id}/approve
POST /api/v1/runs/{run_id}/proposals/{proposal_id}/reject
```

Scenario 3 uses existing:

`RunStateResponse`

No new Scenario 3 Run-state schema is required.

---

# 27. Frontend impact

Current console data model already supports Scenario 3.

Minimal Phase 8 frontend changes planned:

- add `startScenario3()`;
- add Scenario 3 launch option;
- derive console title from `state.run.scenario_id`;
- remove hard-coded Scenario 1 navigation labels where needed.

Existing generic views can show:

- Incident;
- Evidence;
- Proposal;
- Approval;
- action;
- WorkOrder;
- persisted timeline.

No separate Scenario 3 console architecture is needed.

---

# 28. Phase 8 implementation checkpoints

## 8C1 — DONE / PASS
### Product foundation + Scenario 3 provider reads

No Gemini dependency for PASS.

Implement:

- structured Scenario 3 bootstrap context;
- Scenario 3 fixture/bootstrap;
- `POST /api/v1/scenario-3/runs`;
- persisted safe service/symptom fields;
- provider source adapter;
- Scenario 3 provider read service;
- dependency/status Evidence.

Required deterministic PASS:

- one Product Run;
- one real device Incident;
- event/outbox atomically persisted;
- existing `AGENT_DISPATCH_TOPIC`;
- provider context bound to persisted Product facts;
- dependency mapping persisted;
- AcmePay HEALTHY status persisted;
- unknown service/dependency rejected;
- tenant/run isolation;
- no new schema;
- `alembic check` clean.

Phase 8C1 implementation result:

- branch: `phase-8c1-scenario3-provider-reads`;
- implementation checkpoint: `ceccf0f59950105e71fb35435118d3a26b473497`;
- deterministic CI run: `37491364260` — SUCCESS;
- `POST /api/v1/scenario-3/runs` creates one real device Incident and persists the existing generic device-Incident outbox envelope atomically;
- Scenario 3 safe bootstrap persists `service_key=payment_gateway` and `symptom_key=payment_gateway_timeout` only in the existing initial Product signal shape;
- provider reads are bound to those persisted Product facts;
- external dependency status can be read only after same-run `SERVICE_DEPENDENCY_MAPPING` Evidence establishes the dependency ID;
- canonical AcmePay status is persisted as `EXTERNAL_DEPENDENCY_STATUS=HEALTHY`;
- unknown service/dependency and tenant/run context mismatches fail closed, including same-tenant/different-run Evidence isolation;
- post-implementation review found that omitting `wake()` was not enough because the existing Scenario 1 worker continuously polls the shared generic topic;
- 8C1 now fails closed at dispatch: if persisted `Run.scenario_id != "scenario-1"`, the Scenario 1 worker reschedules the envelope and never invokes Scenario 1 native runtime;
- this guard is temporary boundary protection only; actual Scenario 1/3 runtime selection remains 8C2 scope;
- no Scenario 3 table or migration was added; Alembic remains `20261006_0006`;
- no native Scenario 3 ADK runtime, tool wrappers, Scenario 1/3 worker routing, HITL changes or replanning logic were added in 8C1.

## 8C2 — DONE / PASS
### Native Scenario 3 composition + shared runtime routing

Branch:

`phase-8c2-scenario3-native-routing`

Reviewed implementation checkpoint:

`9d9d6f2a44b709c6d443e9608e4d3e026ccb0470`

Deterministic GitHub Actions run:

`37504606915` — **SUCCESS**

Implemented:

- exact Scenario 3 Product/ADK tool surface:
  - `get_service_dependencies`
  - `get_external_dependency_status`
  - `get_device`
  - `get_site_health`
  - `run_diagnostic`
  - `search_kb`
  - `propose_field_visit`
  - native `await_human_decision`;
- no `search_incidents`, local-service/Major-Incident Scenario 2 tools or
  `propose_major_incident` are exposed to Scenario 3;
- trusted `tenant_id` / `run_id` remain hidden from model-visible arguments
  and are derived from native ADK `ToolContext`;
- the device-Incident native lifecycle is shared through one
  `DeviceIncidentAgentRuntime`; Scenario 1 and Scenario 3 are thin
  scenario-specific configurations over the same session/invocation/resume
  machinery;
- one Product Run still maps to one native Session with `session_id == run_id`;
- the existing generic device-Incident worker remains the only consumer of
  `AGENT_DISPATCH_TOPIC` and now selects Scenario 1 vs Scenario 3 runtime from
  persisted `Run.scenario_id`;
- no third worker and no Scenario 3 topic were created;
- Scenario 3 start ensures the same persistent native ADK Session and wakes the
  shared durable worker only after Product state/outbox commit;
- existing generic Field Service Approve/Reject endpoints now select the native
  resume runtime from persisted `Run.scenario_id` after Product decision
  commit;
- a post-commit runtime-selection/read failure leaves the Product decision
  committed and returns native resume as deferred/retryable rather than turning
  committed truth into an ambiguous 500;
- Field Service native HITL is hardened: an
  `await_human_decision(PROPOSAL-X)` pause is valid only after a successful
  same-invocation `propose_field_visit` response for exactly `PROPOSAL-X`
  with `PENDING_APPROVAL`;
- a mismatched wait, a wait without a successful Product proposal, or a Product
  proposal without an exact native wait cannot be treated as a safely delivered
  HITL point;
- shared native human-decision correlation also requires the successful Product
  proposal response, preventing a bare model-supplied proposal ID from creating
  a resume link;
- Scenario 2 implementation was not refactored into Scenario 3;
- no Product-side Scenario 3 replanning branch and no artificial provider-health
  Field Service prerequisite were added.

Historical regression note:

The first full 8C2 run exposed one Phase 7A synthetic redelivery fixture that
created a bare native wait without a prior Product proposal response. The fixture
was corrected to represent the now-valid
`propose_field_visit(PENDING_APPROVAL) -> exact await_human_decision` trace.
Production safety was not weakened.

Verification on the reviewed code checkpoint:

- focused Phase 8C1 regression: **5 passed**;
- focused Phase 8C2 tests: **8 passed**;
- full Python regression: **208 passed**;
- retained historical Node regression: **5 passed**;
- frontend tests: **42 passed**;
- frontend typecheck/lint/build/static audit: PASS;
- Product Docker image build: PASS;
- Alembic remains `20261006_0006 (head)`;
- `alembic check`: **No new upgrade operations detected**.

Post-implementation review correction:

- a real stale-path composition defect was found after the initial 8C2 PASS;
- Scenario 3 diagnostic reads and Field Service approval revalidation had been
  wired to separate fixture instances with independent process-local
  access-link override stores;
- the two scenario fixture objects now share one authoritative access-link
  override store while retaining separate bootstrap identities;
- this guarantees that a Scenario 3 `DOWN -> UP` source-truth change is seen by
  the existing Field Service approval revalidation path;
- focused regression coverage was added for this shared stale truth;
- the corrected exact code checkpoint is
  `9d9d6f2a44b709c6d443e9608e4d3e026ccb0470`;
- deterministic GitHub Actions run `37504606915` is SUCCESS.

## 8D
### Deterministic Scenario 3 E2E + recovery/regressions + minimal UI exposure

Use scripted/model-double behavior with real Product stack.

Prove:

- provider investigation first;
- mapping Evidence;
- AcmePay HEALTHY Evidence;
- local domain entered only after provider disconfirmation;
- local root cause independently proven;
- Field Service proposal;
- native HITL;
- Approve;
- replay;
- Reject;
- stale;
- restart/redelivery;
- no hidden CoT persistence;
- Scenario 1/2 full regressions;
- frontend can start/view Scenario 3.

## 8E
### Managed live acceptance

Use:

- managed Product API;
- PostgreSQL;
- real Gemini;
- native Google ADK.

Must prove with real trace:

1. persisted Scenario 3 Run + Incident;
2. one persistent native Session;
3. dependency mapping;
4. AcmePay HEALTHY Product Evidence;
5. no local/device investigation before provider disconfirmation;
6. subsequent local diagnostic tools in same Run/Session;
7. CMDB/site/access-link/KB Evidence;
8. Field Service proposal;
9. native HITL pause;
10. human Approve;
11. Product revalidation;
12. exactly one action;
13. exactly one WorkOrder;
14. same invocation resumed;
15. replay creates no duplicates.

Record exact branch/SHA/CI/deployment/Run/Session/invocation/proposal/approval/action/WorkOrder IDs.

---

# 29. Hard invariants carried forward

1. Product business event is persisted before agent dispatch.
2. One Product Run = one persistent native ADK Session.
3. `session_id = run_id`.
4. Product owns business truth and Evidence.
5. ADK owns generic runtime/session/event/invocation continuity.
6. Hidden chain-of-thought is not Product state/UI.
7. Model never chooses trusted `tenant_id` or `run_id`.
8. Product must not perform Scenario 3 replanning.
9. Tool failure is not evidence.
10. Provider HEALTHY does not itself prove local root cause.
11. Local Field Service proposal still requires real local Evidence.
12. Side effect only after Product human approval and revalidation.
13. Replay/retry/concurrent decisions cannot duplicate execution.
14. Restart preserves Product truth + native Session/HITL correlation.
15. No second generic runtime/session/resume framework.
16. Scenario 1 regression remains mandatory.
17. Scenario 2 regression remains mandatory.

---

# 30. Known debt / non-Phase-8 redesign

Do not reopen without a reproducible defect:

- completed Phase 0–7 ownership boundaries;
- Scenario 2 Major Incident domain;
- Scenario 2 live-validated read/proposal/HITL flow;
- native ADK session persistence;
- generic SSE recovery architecture.

Known UI debt remains:

> light / white UI polish must be closed no later than Phase 9 unless explicitly pulled forward.

Known provider limitation remains:

> Gemini managed acceptance previously observed a 15 requests/minute quota.

Deterministic Phase 8 gates must not depend on provider quota.

---

# 31. Next executor instruction

Start from Phase 8C2 reviewed implementation checkpoint:

`9d9d6f2a44b709c6d443e9608e4d3e026ccb0470`

Branch:

`phase-8c2-scenario3-native-routing`

Next task:

> **Implement Phase 8D only.**

Phase 8D is the deterministic Scenario 3 E2E/recovery/regression/UI checkpoint.
Use scripted/model-double behavior with the real Product stack; do not depend on
Gemini quota.

Required proof:

1. provider-domain investigation occurs first;
2. `SERVICE_DEPENDENCY_MAPPING` Evidence establishes AcmePay;
3. authoritative `EXTERNAL_DEPENDENCY_STATUS=HEALTHY` is persisted;
4. no local/device diagnostic investigation occurs before provider
   disconfirmation;
5. the same Run/native Session then enters local/device diagnosis;
6. CMDB, site-health, access-link and approved KB Evidence independently support
   `LOCAL_ACCESS_LINK_FAILURE`;
7. Field Service proposal is created;
8. exact native HITL pause is established;
9. Approve, replay, Reject and stale paths are deterministic;
10. restart/redelivery preserves the same Product truth and native invocation
    continuity;
11. no hidden chain-of-thought is persisted;
12. Scenario 1 and Scenario 2 full regressions remain PASS;
13. minimal frontend exposure can start and view Scenario 3.

Do not move real Gemini/managed acceptance into 8D. That remains Phase 8E.

Do not create a new worker/topic/runtime framework, new Scenario 3 business
tables, Product-side replanning rules, or provider-health proposal prerequisites.

---

# 32. Current canonical stop point

> **Phase 7 = DONE / PASS**  
> **Phase 8A = DONE / DESIGN PASS**  
> **Phase 8B = DONE / REVIEWED DESIGN PASS**  
> **Phase 8C1 = DONE / PASS**  
> **Phase 8C2 = DONE / PASS**  
> **Phase 8D = NEXT**

Phase 8C2 is deterministically verified on
`9d9d6f2a44b709c6d443e9608e4d3e026ccb0470` with GitHub Actions run
`37504606915` SUCCESS. Managed/live Phase 8 acceptance remains deferred to
Phase 8E.
