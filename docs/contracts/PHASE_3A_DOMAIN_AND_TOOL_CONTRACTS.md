# Фаза 3A — Domain design и tool contracts Scenario 1

Дата: 4 октября 2026 года.  
Статус: **3A implementation checkpoint / design freeze**.

Документ основан на canonical cumulative handoff v5.5 и
`PHASE_2_TOOL_AND_DOMAIN_CONTRACTS.md`. Он фиксирует продуктовую модель
Scenario 1 перед Фазой 3B. Это не спецификация БД, API, SSE или UI.

## 1. Scope 3A

Фаза 3A:

1. разделяет pure domain model, repository/source-system ports и ADK-facing
   tool adapters;
2. фиксирует request/result schemas и error taxonomy для Scenario 1;
3. фиксирует domain entities, ownership `tenant_id/run_id` и state transitions;
4. фиксирует evidence/proposal/approval shapes, которые будет реализовывать 3B.

Фаза 3A **не** реализует PostgreSQL, product FastAPI routes, SSE, UI, concrete
repositories, evidence validator, approval execution и подключение шести
Scenario 1 tools к живому ADK agent.

Существующие `phase1_adk_spike/` и `phase2_backend/` остаются отдельным
runtime proof и не превращаются в product backend.

## 2. Границы слоёв

```text
ADK agent
   |
   | model-visible request
   v
Scenario1ToolAdapter
   |
   | trusted ToolCallContext(tenant_id, run_id)
   v
domain/application operation
   |                         \
   |                          \ product repositories
   v                           v
CMDB / Monitoring / ITSM / KB ports   Run/Evidence/Proposal/... repositories
```

### Pure domain

`product_backend/domain/` содержит только доменные types/enums/errors и
контракты переходов. Здесь нет FastAPI, Google ADK, PostgreSQL driver или
provider SDK.

### Source-system ports

`product_backend/ports/source_systems.py` фиксирует provider-neutral границы:

- `CmdbPort` — topology/device lookup;
- `MonitoringPort` — site health и diagnostics;
- `ItsmPort` — incident lookup/search;
- `KnowledgeBasePort` — deterministic KB search.

Mock или будущая реальная интеграция могут меняться за этой границей без
изменения model-visible tool contract.

### Product repositories

`product_backend/ports/repositories.py` фиксирует интерфейсы хранения
product-owned state: run, incident, evidence, proposal, approval,
executed action и work order. Реализации хранилища в 3A нет.

Отдельно объявлен `ApprovalExecutionUnitOfWork`: будущий approve/execute
должен атомарно повторно проверить состояние и сохранить решение, transition,
executed action, work order и incident state.

### Tool adapter

`Scenario1ToolAdapter` фиксирует шесть ADK-facing операций. В 3A это boundary,
а не concrete implementation.

## 3. Trusted context и model-visible input

Модель не выбирает authoritative tenant/run context.

Trusted context:

```text
ToolCallContext
- tenant_id
- run_id
```

Он инжектируется application/adapter layer и отсутствует во всех
model-visible request schemas.

Секреты, DB handles, approval endpoint и hidden fixture truth также никогда не
являются tool arguments модели.

## 4. Domain entities

### Run

Поля: `run_id`, `tenant_id`, `scenario_id`, status, timestamps.

Statuses:

```text
CREATED
ACTIVE
WAITING_APPROVAL
COMPLETED
FAILED
```

Transitions:

```text
CREATED -> ACTIVE | FAILED
ACTIVE -> WAITING_APPROVAL | COMPLETED | FAILED
WAITING_APPROVAL -> ACTIVE | COMPLETED | FAILED
COMPLETED -> terminal
FAILED -> terminal
```

`WAITING_APPROVAL -> ACTIVE` нужен для продолжения той же ADK session после
зафиксированного human decision/result, без зависшего tool call.

### Incident

Поля: incident/tenant/run/site/device IDs, symptom, status, timestamps.

Общий status vocabulary включает `OPEN`, `ESCALATED`, `RESOLVED`, но
Scenario 1 field-visit flow разрешает только:

```text
OPEN -> ESCALATED
```

Сам факт создания field-service work order не доказывает восстановление и не
даёт права переводить incident в `RESOLVED`.

### DeviceTopology

Authoritative CMDB observation:

- `device_id`
- `site_id`
- `attachment_id`
- `device_type`
- `expected_switch_id`
- `expected_port_id`

Attachment/switch/port IDs должны быть получены из tool result, а не из hidden
fixture или initial prompt.

### SiteHealthSnapshot

Typed observation о site network, payment service, peer reachability и
affected-device reachability. Это observation, не diagnosis.

### AccessLinkDiagnosticSnapshot

Typed поля diagnostic target, attachment, switch/port, switch reachability,
admin/operational state, port-security и configuration state. Validators в 3B
должны опираться на эти поля, а не парсить prose.

### IncidentSearchSnapshot

Scope, entity ID и найденные open incident IDs. Этот evidence полезен агенту,
но не является одним из четырёх обязательных evidence classes для
`LOCAL_ACCESS_LINK_FAILURE`.

### KbArticle

Typed KB result: article ID, title, approved flag, diagnosis codes, allowed
actions и stable `guidance_code`. Validator не должен извлекать policy из
свободного текста статьи.

### Evidence

Immutable record:

```text
evidence_id
tenant_id
run_id
source_type
captured_at
entity_ids
typed payload
facts[]          # только aid для UI/agent
expires_at       # optional TTL boundary
```

Canonical source types:

- `CMDB_SNAPSHOT`
- `SITE_HEALTH`
- `ACCESS_LINK_DIAGNOSTIC`
- `INCIDENT_SEARCH`
- `KB_ARTICLE`

`facts` не authoritative. Validator должен читать typed payload,
tenant/run ownership и timestamps.

### ActionProposal

Поля: proposal/tenant/run/incident/device IDs, diagnosis, action type,
evidence IDs, rationale, status, timestamps и server-derived parameters.

Model-visible request **не содержит** queue, address, engineer или arbitrary
work type. Для этого tool action фиксирован как `ONSITE_FIELD_VISIT`.

### Approval

Отдельная immutable сущность human decision: approval ID, tenant/run/proposal,
`APPROVED|REJECTED`, timestamp и actor. Approval не является model tool.

### ExecutedAction / FieldServiceWorkOrder

Отдельные immutable записи фактического исполнения после approval. Proposal не
равен execution.

Для work order пока фиксируется только статус `CREATED`; dispatch/completion
lifecycle текущими документами не специфицирован и не придумывается в 3A.

### DeviceResolution

После создания work order устройство Scenario 1 остаётся `UNRESOLVED`.
Work order сам по себе не является repair evidence.

## 5. Proposal state contract

Statuses:

```text
PENDING_APPROVAL
REJECTED
STALE
EXECUTED
```

Transitions:

```text
PENDING_APPROVAL -> REJECTED
PENDING_APPROVAL -> STALE
PENDING_APPROVAL -> EXECUTED
```

Отдельного proposal-status `APPROVED` нет: approval — отдельная сущность.
После Approve domain layer в транзакции заново проверяет актуальность. Если
условия исчезли — proposal становится `STALE`; если всё валидно —
`EXECUTED`.

Все terminal proposal states не имеют outgoing transitions.

## 6. Tool contracts Scenario 1

Ровно шесть model-visible tools:

1. `get_device(device_id)`
2. `get_site_health(site_id)`
3. `run_diagnostic(diagnostic_type, target_id)`
4. `search_incidents(scope, entity_id)`
5. `search_kb(query)`
6. `propose_field_visit(...)`

### get_device

Input: `device_id`.

Success сохраняет Phase 2-compatible поля `device_id` и `attachment_id`,
добавляя `site_id`, `device_type`, typed topology и `CMDB_SNAPSHOT`
evidence.

### get_site_health

Input: `site_id`.

Success: typed `SiteHealthSnapshot` + `SITE_HEALTH` evidence.

### run_diagnostic

Input:

```text
diagnostic_type: ACCESS_LINK
target_id: string
```

Target должен быть уже известным допустимым объектом текущего context; adapter
не должен позволять model использовать произвольный cross-tenant target.

Success: typed diagnostic snapshot + `ACCESS_LINK_DIAGNOSTIC` evidence.

### search_incidents

Input: `scope: DEVICE|SITE`, `entity_id`.

Success: open incident IDs + `INCIDENT_SEARCH` evidence. Фиксированной позиции
этого tool в расследовании нет.

### search_kb

Input: model-chosen `query`. Retrieval в mock KB остаётся deterministic.
Success возвращает typed articles + `KB_ARTICLE` evidence. Article ID не
должен заранее попадать в prompt.

### propose_field_visit

Model-visible input:

```text
incident_id
device_id
diagnosis
evidence_ids[]
rationale
```

Нет model-visible:

- tenant/run;
- queue/address/engineer;
- arbitrary work type;
- approve/reject;
- execute/dispatch.

Успех создаёт только `PENDING_APPROVAL` proposal. Это единственная разрешённая
agent-side mutation в Scenario 1 tool surface; execution не происходит.

## 7. Evidence requirements для 3B

Для proposal с `LOCAL_ACCESS_LINK_FAILURE` validator должен требовать current
same-tenant/same-run evidence всех четырёх классов:

1. `CMDB_SNAPSHOT`: terminal -> attachment -> expected switch/port;
2. `SITE_HEALTH`: site/payment healthy, peer reachable, affected terminal
   unreachable;
3. `ACCESS_LINK_DIAGNOSTIC`: expected switch reachable, admin UP,
   operational DOWN, normal port security, expected configuration;
4. `KB_ARTICLE`: approved/current KB допускает onsite physical-path
   inspection для этого observation pattern.

Missing, stale, wrong-entity или cross-context evidence должен приводить к
`INSUFFICIENT_OR_INVALID_EVIDENCE` на proposal boundary. Rationale модели не
является доказательством.

## 8. Error taxonomy

### Input/context

- `INVALID_ARGUMENT`
- `CONTEXT_MISMATCH`

### CMDB/topology

- `DEVICE_NOT_FOUND`
- `SITE_NOT_FOUND`
- `ATTACHMENT_NOT_FOUND`

### Monitoring/diagnostics

- `SITE_HEALTH_UNAVAILABLE`
- `DIAGNOSTIC_UNAVAILABLE`
- `DIAGNOSTIC_TARGET_NOT_FOUND`
- `UNSUPPORTED_DIAGNOSTIC`

### ITSM/KB

- `INCIDENT_NOT_FOUND`
- `INCIDENT_SEARCH_UNAVAILABLE`
- `KB_UNAVAILABLE`

### Shared integration

- `UPSTREAM_UNAVAILABLE`

### Evidence/proposal/state

- `EVIDENCE_NOT_FOUND`
- `EVIDENCE_EXPIRED`
- `EVIDENCE_CONTEXT_MISMATCH`
- `INSUFFICIENT_OR_INVALID_EVIDENCE`
- `INVALID_PROPOSAL`
- `PROPOSAL_NOT_FOUND`
- `PROPOSAL_NOT_PENDING`
- `INVALID_STATE_TRANSITION`

Phase 2 codes `DEVICE_NOT_FOUND`, `ATTACHMENT_NOT_FOUND`,
`DIAGNOSTIC_UNAVAILABLE` и `UPSTREAM_UNAVAILABLE` сохранены.

Consumer принимает решения по `error.code`, не по human-readable message.
Raw exception, provider payload, stack trace и secrets наружу не выходят.

## 9. Ownership/isolation

- run принадлежит одному `tenant_id`;
- incident/evidence/proposal/approval/execution/work-order связаны с одним
  tenant/run context;
- evidence другого tenant/run не может подтверждать proposal;
- source adapters не принимают model-selected tenant/run;
- repository read interfaces для run-scoped state требуют tenant + run;
- hidden fixture может содержать больше данных, чем model-visible observation.

## 10. Approval/execution semantics, зарезервированные для 3B

3A уже фиксирует следующие правила реализации 3B:

1. agent создаёт только `PENDING_APPROVAL`;
2. human approve/reject — application endpoint, не ADK tool;
3. Approve транзакционно перепроверяет pending proposal, open incident/device
   ownership, link still DOWN и отсутствие existing work order/equivalent
   executed action;
4. Approved, но уже неактуальный proposal -> `STALE`, без execution;
5. Approved + valid -> ровно один `ExecutedAction`, один
   `FieldServiceWorkOrder`, proposal `EXECUTED`, incident `ESCALATED`,
   device `UNRESOLVED`;
6. повторный Approve idempotent и возвращает stored result;
7. Reject -> `REJECTED`, zero execution, incident остаётся open;
8. после commit application может передать actual result в ту же ADK session.

`ApprovalExecutionUnitOfWork` — только архитектурная граница для будущей
транзакции, не реализация БД.

## 11. Что сознательно отложено

Не входит в 3A:

- TTL evaluation;
- evidence/proposal validator implementation;
- approve/reject service;
- idempotency implementation;
- mock/PostgreSQL repositories;
- product FastAPI routes;
- persistence/SSE/UI;
- wiring шести tools в живой ADK agent;
- изменение двух-tool Phase 1/2 spike.

## 12. Acceptance 3A

3A считается готовой к review, если:

- product domain физически отделён от spike;
- pure domain не импортирует ADK/FastAPI/DB;
- объявлены ровно шесть Scenario 1 tools;
- model-visible request не содержит `tenant_id/run_id`;
- field-visit request не позволяет выбрать dispatch-параметры;
- сохранены нужные Phase 2 error contracts;
- transitions отражают Scenario 1 semantics;
- repository/source-system interfaces существуют без persistence;
- contract tests проходят;
- PostgreSQL/UI/SSE/live mutation endpoint не добавлены.

После review этого design freeze можно переходить к 3B.
