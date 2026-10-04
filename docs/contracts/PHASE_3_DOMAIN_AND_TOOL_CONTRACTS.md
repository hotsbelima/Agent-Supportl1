# Phase 3 — Product domain and tool contracts

Дата: 4 октября 2026 года.  
Статус: **PASS**.

Этот документ является финальной контрактной точкой Фазы 3 и supersede-ит
`PHASE_3A_DOMAIN_AND_TOOL_CONTRACTS.md` как актуальное описание product-domain
Scenario 1. Phase 3A документ сохраняется как design checkpoint.

## 1. Что завершено

Фаза 3 разделила runtime spike и настоящий product-domain Scenario 1:

- pure domain model;
- repository/source-system ports;
- шесть model-visible tool contracts;
- concrete tool adapter integration;
- immutable evidence;
- deterministic evidence/proposal validation;
- human approval/execution boundary;
- stale/idempotency semantics;
- regression/CI gate.

`phase1_adk_spike/` и `phase2_backend/` остаются отдельным доказанным
runtime probe и не являются product backend.

## 2. Product layers

```text
future ADK function wrappers
        |
        | model-visible request only
        v
DefaultScenario1ToolAdapter
        |
        +--> trusted ToolCallContext(tenant_id, run_id)
        |
        +--> CMDB / Monitoring / ITSM / KB ports
        |
        +--> immutable Evidence repository
        |
        +--> FieldVisitProposalService
                    |
                    v
            deterministic validators
                    |
                    v
            proposal / approval domain
```

Модель не выбирает `tenant_id`, `run_id`, approval decision, work-order
routing или persistence handles.

## 3. Шесть Scenario 1 tools

Model-visible surface фиксирован:

1. `get_device(device_id)`
2. `get_site_health(site_id)`
3. `run_diagnostic(diagnostic_type, target_id)`
4. `search_incidents(scope, entity_id)`
5. `search_kb(query)`
6. `propose_field_visit(incident_id, device_id, diagnosis, evidence_ids, rationale)`

Первый пять tools — read-only observations. Шестой создаёт только
`PENDING_APPROVAL` proposal; execution не является tool модели.

## 4. Ownership и ID safety

Все model calls получают trusted `ToolCallContext` от application layer.

Concrete adapter до provider call проверяет:

- run существует и находится в `ACTIVE`;
- device/site/search entity уже принадлежит текущему run или был открыт
  предыдущим evidence;
- diagnostic target является canonical attachment, ранее полученным из
  `CMDB_SNAPSHOT`;
- CMDB topology не уводит device в неизвестный site;
- site health не подменяет affected device;
- diagnostic switch/port совпадают с canonical CMDB topology.

Таким образом модель не может превратить произвольный угаданный ID в
authoritative observation.

После создания proposal run переходит в `WAITING_APPROVAL`; read tools в этом
состоянии не выполняются. После human decision run возвращается в `ACTIVE`.

## 5. Evidence

Каждая успешная read operation создаёт immutable `Evidence`:

```text
evidence_id
tenant_id
run_id
source_type
captured_at
entity_ids
typed payload
facts[]       # non-authoritative
expires_at
```

Source types:

- `CMDB_SNAPSHOT`
- `SITE_HEALTH`
- `ACCESS_LINK_DIAGNOSTIC`
- `INCIDENT_SEARCH`
- `KB_ARTICLE`

`facts` никогда не парсится validator-ом как источник истины.

Dynamic evidence (`SITE_HEALTH`, `ACCESS_LINK_DIAGNOSTIC`) обязано иметь
положительный TTL. Конкретные TTL являются application configuration через
`EvidenceTtlPolicy`, а не model-visible параметрами и не захардкожены в
domain contract.

## 6. Proposal validator

Для `LOCAL_ACCESS_LINK_FAILURE + ONSITE_FIELD_VISIT` требуются одновременно
same-tenant/same-run current evidence:

1. CMDB: terminal -> attachment -> expected switch/port;
2. Site health: site/payment healthy, peer reachable, affected device
   unreachable;
3. Access-link diagnostic: canonical attachment/switch/port, switch reachable,
   admin UP, operational DOWN, normal port security, expected configuration;
4. Approved KB: article разрешает этот diagnosis/action.

Validator проверяет typed payload, `entity_ids`, TTL и ownership. Missing,
foreign, stale, inconsistent или incomplete set даёт
`INSUFFICIENT_OR_INVALID_EVIDENCE`.

## 7. Proposal и state transitions

Scenario 1 proposal states:

```text
PENDING_APPROVAL -> REJECTED
PENDING_APPROVAL -> STALE
PENDING_APPROVAL -> EXECUTED
```

Terminal proposal states не имеют outgoing transitions.

Scenario 1 incident flow для field visit:

```text
OPEN -> ESCALATED
```

Создание work order не является repair evidence и не переводит incident в
`RESOLVED`.

## 8. Human approval/execution boundary

Approve/Reject — application operation, не model tool.

При Approve:

1. proposal должен всё ещё быть `PENDING_APPROVAL`;
2. incident должен быть OPEN, а device всё ещё принадлежать incident;
3. backend заново читает current CMDB topology;
4. backend заново выполняет current access-link diagnostic;
5. проверяется отсутствие existing work order / equivalent executed action.

Если authoritative state показывает, что условие исчезло, human decision
сохраняется как APPROVED, proposal -> `STALE`, execution = 0.

Если provider временно недоступен и fresh revalidation невозможно выполнить,
approval **не потребляется**: proposal остаётся `PENDING_APPROVAL`, наружу
возвращается безопасная retryable typed error.

Если всё валидно:

- создаётся ровно один `ExecutedAction`;
- создаётся ровно один `FieldServiceWorkOrder`;
- proposal -> `EXECUTED`;
- incident -> `ESCALATED`;
- run -> `ACTIVE`.

Work-order topology fields (`site_id`, `attachment_id`, `switch_id`,
`port_id`) выводятся из trusted current CMDB, а не из model request.

Reject:

- decision = REJECTED;
- proposal -> `REJECTED`;
- zero execution;
- incident остаётся OPEN;
- run -> `ACTIVE`.

Повтор того же human decision возвращает stored result и не создаёт второй
action/work order. Конфликтующий второй decision отклоняется.

Настоящая защита от двух конкурентных HTTP transactions должна быть
дополнительно обеспечена будущей persistence implementation через transaction
и unique constraints; repository contracts уже фиксируют эти invariants.

## 9. Source-port result semantics

Для revalidation различаются authoritative absence и outage:

- `None` от port = authoritative not-found/absence -> условие исчезло,
  proposal может стать `STALE`;
- exception от port = provider/transport unavailable -> safe retryable typed
  error, approval не потребляется.

Raw exception text, stack trace или secrets наружу не передаются.

## 10. Error taxonomy

Сохраняется typed taxonomy Фазы 3A, включая:

- `INVALID_ARGUMENT`
- `CONTEXT_MISMATCH`
- `DEVICE_NOT_FOUND`
- `SITE_NOT_FOUND`
- `ATTACHMENT_NOT_FOUND`
- `SITE_HEALTH_UNAVAILABLE`
- `DIAGNOSTIC_UNAVAILABLE`
- `DIAGNOSTIC_TARGET_NOT_FOUND`
- `UNSUPPORTED_DIAGNOSTIC`
- `INCIDENT_NOT_FOUND`
- `INCIDENT_SEARCH_UNAVAILABLE`
- `KB_UNAVAILABLE`
- `UPSTREAM_UNAVAILABLE`
- `INSUFFICIENT_OR_INVALID_EVIDENCE`
- `INVALID_PROPOSAL`
- `PROPOSAL_NOT_FOUND`
- `PROPOSAL_NOT_PENDING`
- `INVALID_STATE_TRANSITION`

Consumer принимает решения по `error.code`, не по свободному message.

## 11. Repository/application boundaries

Фаза 3 фиксирует ports, но не concrete PostgreSQL implementation:

- `RunRepository`
- `IncidentRepository`
- `EvidenceRepository`
- `ProposalRepository`
- `ApprovalRepository`
- `ExecutedActionRepository`
- `WorkOrderRepository`
- `ToolReadUnitOfWork`
- `ProposalCreationUnitOfWork`
- `ApprovalExecutionUnitOfWork`

Persistent implementation обязана обеспечить transactionality и uniqueness
approval/action/work-order invariants.

## 12. Проверка

GitHub Actions `Phase 3 domain check` выполняет два уровня:

### Domain gate

```text
python -m compileall -q product_backend
python -m pytest -q   tests/test_phase3a_contracts.py   tests/test_phase3b_domain_logic.py   tests/test_phase3c_contract_integration.py
```

Результат на финальном Phase 3 checkpoint: **51 passed**.

### Full repository regression

Используются pinned `requirements.txt` и Python 3.12.14:

```text
pip check
compileall product_backend phase1_adk_spike phase2_backend
pytest -q
npm test
```

Финальный результат:

- `pip check`: no broken requirements;
- Python: **59 passed, 1 dependency deprecation warning**;
- retained Node spike tests: **5 passed, 0 failed**.

Warning относится к FastAPI/Starlette TestClient dependency surface и не
является Phase 3 regression.

## 13. Что Фаза 3 намеренно не делает

Фаза 3 не добавляет:

- PostgreSQL implementation;
- product FastAPI routes;
- persisted event log/outbox;
- SSE;
- UI;
- auth/rate limiting;
- live six-tool ADK wiring;
- Scenario 2/3 product logic.

Это следующий слой поверх уже устойчивой domain foundation.

## 14. Следующий шаг

После Phase 3 PASS можно подключать persistence/application delivery layer:

1. PostgreSQL schema + repository/UoW implementations;
2. application events/outbox;
3. product FastAPI endpoints, включая start/run и human approval;
4. persisted SSE stream;
5. затем UI;
6. после этого — live ADK wiring шести Scenario 1 tools и E2E acceptance.

Порядок может быть уточнён отдельным планом следующей фазы, но domain rules
Фазы 3 не должны переноситься в API/UI/LLM layer.
