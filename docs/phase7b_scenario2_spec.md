# Phase 7B — Canonical Scenario 2 specification

Status: contract/spec checkpoint only. Phase 7C ingestion, Phase 7D live ADK tools/HITL,
and Phase 7E managed acceptance are intentionally out of scope.

## Business case

Network: **8 Щупалец**.

Scenario 2 demonstrates sequential operational facts from geographically independent
stores that eventually support a Product-owned proposal to create a Major Incident.
The backend must not decide correlation from event count. The model must use persisted
signals plus typed tool evidence.

Canonical correlation key:

`payment_gateway_timeout`

Canonical business service:

`payment_gateway`

Canonical common external dependency:

- ID: `DEP-ACMEPAY-PAYMENTS`
- Name: `AcmePay`
- Kind: external provider
- Happy-path authoritative state: `DEGRADED`

No matching Major Incident exists initially.

## Canonical sites and Product ServiceIncidents

Scenario 1 Incident is device-centric, so Scenario 2 uses a dedicated typed
ServiceIncident rather than fabricating reported_device_id.

| Site | Role | ServiceIncident |
| --- | --- | --- |
| `SITE-KZN-017` | first affected store | `INC-S2-KZN-001` |
| `SITE-SAM-024` | geographically independent affected store | `INC-S2-SAM-001` |

A ServiceIncident represents a real site/service operational problem, **not every
incoming signal**. A repeat ticket/alert for the same site remains an operational
signal fact associated with the existing ServiceIncident.

## Exact incoming sequence

1. `SIG-S2-001` — source `MONITORING`, site `SITE-KZN-017`,
   source ref `MON-ALERT-KZN-901`, correlation key
   `payment_gateway_timeout`. This creates/resolves the first site Incident
   `INC-S2-KZN-001`.
2. `SIG-S2-002` — source `ITSM`, site `SITE-KZN-017`,
   source ref `TICKET-KZN-5521`, same correlation key. This is persisted as a
   second fact associated with `INC-S2-KZN-001`; it does **not** create a second
   Product Incident and does not prove cross-site outage.
3. `SIG-S2-003` — source `MONITORING`, site `SITE-SAM-024`,
   source ref `MON-ALERT-SAM-337`, same correlation key. This creates/resolves
   `INC-S2-SAM-001` and supplies the first geographically independent site fact.

All received timestamps are server UTC timestamps assigned by Product ingestion.
Fixture source timestamps, if present in safe payload, are informational and never
replace the server timestamp.

## Hidden deterministic world truth

The initial incoming signals do **not** contain the conclusion “AcmePay outage”.

Authoritative fixture truth available only through future typed source adapters:

- local network at both sites: `HEALTHY`;
- local payment stack at both sites: `HEALTHY`;
- service dependency mapping: `payment_gateway -> DEP-ACMEPAY-PAYMENTS / AcmePay`;
- AcmePay status: `DEGRADED`;
- matching existing Major Incident search: none.

This permits the model to move from “possibly local” to “common dependency” only
through persisted facts and evidence-backed tool calls.

## Typed Scenario 2 evidence

The contract introduces five evidence classes:

1. `OPERATIONAL_SIGNAL` — immutable observation derived from one persisted signal.
2. `LOCAL_SERVICE_HEALTH` — dynamic local network/service health for one site.
3. `SERVICE_DEPENDENCY_MAPPING` — mapping from business service to dependency.
4. `EXTERNAL_DEPENDENCY_STATUS` — dynamic authoritative provider status.
5. `MAJOR_INCIDENT_SEARCH` — dynamic duplicate-prevention search result.

Signal-derived evidence is time-bounded for correlation decisions even though the
underlying Product signal fact remains persisted permanently.

## Proposal and execution

Scenario 2 uses a dedicated `MajorIncidentProposal`; it does **not** reuse
Scenario 1 `ActionProposal` with dummy fields.

Action type is exactly:

`CREATE_MAJOR_INCIDENT`

Proposal identity includes:

- tenant/run;
- correlation key;
- business service key;
- affected site IDs (at least two distinct sites);
- dependency ID/name;
- evidence IDs;
- summary/rationale;
- proposal status/timestamps.

Execution creates a typed `MajorIncidentRecord` and
`MajorIncidentExecution`. No `device_id`, Scenario 1 diagnosis, field-service
action, or WorkOrder exists in these contracts.

## Proposal evidence rules

A valid proposal requires evidence from the same tenant/run and with exact
provenance:

- operational-signal evidence from at least two distinct sites;
- every proposed affected site is supported by signal evidence;
- all signal evidence uses one correlation key matching the proposal;
- fresh local-service-health evidence for every affected site, with local network
  and local payment stack both `HEALTHY`;
- service dependency mapping for `payment_gateway` to the proposed dependency;
- fresh external dependency status showing that dependency is `DEGRADED`;
- fresh Major Incident search for the same correlation/dependency with zero
  matching open Major Incidents.

Single-site evidence is insufficient. Fabricated, missing, expired, cross-tenant,
cross-run, or mismatched evidence is rejected deterministically.

## Approve revalidation

Human Approve is a Product operation. Before execution, Product must revalidate:

- the proposal is still backed by fresh multi-site correlation evidence;
- local-health evidence for all affected sites remains current;
- the common external dependency still maps to the same provider;
- the provider is still `DEGRADED`;
- a matching Major Incident still does not exist.

If the provider recovered or a matching Major Incident now exists, the proposal
becomes `STALE` and execution count stays zero.

A valid Approve creates exactly one typed Major Incident execution/record. Replay or
concurrent duplicate decision must return/reconcile the same result and cannot create
a second equivalent Major Incident.

Reject records the human decision and creates zero execution/records.

Equivalent Major Incident identity is scoped by tenant plus
`(correlation_key, dependency_id)`; persistence in later phases must enforce this
uniqueness for active/created records.

## Optional notification

Mass notification is not an external side effect in Phase 7. If shown later, it may
only be a deterministic Product-owned simulated notification record created after a
successful Major Incident execution.

## Phase boundaries

7B defines the types, canonical fixture, validation rules, and repository/tool
contracts. It does **not**:

- add event ingestion endpoints or simulator sequencing (7C);
- dispatch Scenario 2 events to ADK (7C);
- expose live Scenario 2 ADK tools (7D);
- implement human pause/resume for Scenario 2 (7D);
- create database migrations/tables for Scenario 2 state (7C/7D as required);
- run managed Gemini acceptance (7E).
