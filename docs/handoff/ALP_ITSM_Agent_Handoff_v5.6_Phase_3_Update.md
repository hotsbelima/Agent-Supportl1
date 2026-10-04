# ALP ITSM Agent — Handoff v5.6 / Phase 3 Update

Дата: 4 октября 2026 года.

Этот delta документ фиксирует завершение **Фазы 3 — Product contracts и domain
foundation**. Он дополняет cumulative handoff v5.5 и должен читаться вместе с
новым cumulative handoff v5.6. Runtime spike Фаз 1–2 не заменяется и не
переписывается этой фазой.

## Итог

**Фаза 3: ЗАВЕРШЕНА / PASS.**

Product Scenario 1 теперь имеет отдельный headless domain/application слой,
не смешанный с Phase 1/2 runtime spike:

- pure domain model;
- repository/source-system ports;
- шесть Scenario 1 tool contracts;
- typed error taxonomy;
- tenant/run ownership и state transitions;
- immutable evidence contract;
- deterministic evidence/proposal validation;
- human approval/execution boundary;
- stale/idempotency semantics;
- concrete six-tool adapter integration;
- CI/regression gate.

Фаза была выполнена тремя внутренними checkpoint:

- **3A:** domain design + contracts;
- **3B:** deterministic business logic;
- **3C:** adapter/domain integration + финальный regression.

## Что добавлено/изменено

Основной product code находится в `product_backend/`:

- `domain/models.py` — domain entities;
- `domain/enums.py` — canonical states/codes;
- `domain/errors.py` — safe typed error taxonomy;
- `domain/transitions.py` — run/incident/proposal transitions;
- `domain/validators.py` — deterministic Scenario 1 validators;
- `contracts/tools.py` — model-visible request/result contracts;
- `ports/repositories.py` — persistence/UoW ports и uniqueness invariants;
- `ports/source_systems.py` — CMDB/Monitoring/ITSM/KB ports;
- `adapters/tool_adapters.py` — thin model-facing integration шести Scenario 1 tools;
- `application/read_tools.py` — run/entity ownership, provider orchestration,
  evidence creation и TTL policy;
- `application/field_visit.py` — proposal + human approval/execution services;
- `application/results.py` — application result contracts;
- `contracts/serialization.py` — JSON-safe serialization typed tool results.

Финальный technical contract:
`docs/contracts/PHASE_3_DOMAIN_AND_TOOL_CONTRACTS.md`.

Design checkpoint 3A сохранён отдельно:
`docs/contracts/PHASE_3A_DOMAIN_AND_TOOL_CONTRACTS.md`.

## Шесть Scenario 1 tools

Product tool surface:

1. `get_device(device_id)`;
2. `get_site_health(site_id)`;
3. `run_diagnostic(diagnostic_type, target_id)`;
4. `search_incidents(scope, entity_id)`;
5. `search_kb(query)`;
6. `propose_field_visit(...)`.

Первые пять read-only. `propose_field_visit` создаёт только
`PENDING_APPROVAL` proposal. Approve/Reject/execute не являются tools модели.

Phase 1/2 two-tool spike по-прежнему содержит только `get_device` и
`run_diagnostic`; его нельзя ретроспективно описывать как six-tool product
agent.

## Evidence и validator

Каждый успешный read tool создаёт immutable typed Evidence с tenant/run
context, captured time, entity IDs и payload.

Для `LOCAL_ACCESS_LINK_FAILURE + ONSITE_FIELD_VISIT` proposal требует:

1. CMDB terminal -> attachment -> expected switch/port;
2. healthy site/payment + reachable peer + unreachable affected terminal;
3. canonical access-link diagnostic: switch reachable, admin UP,
   operational DOWN, normal port security, expected configuration;
4. approved KB, разрешающую onsite physical-path inspection.

Validator не доверяет `facts`/LLM rationale и не парсит prose как evidence.
Dynamic site/diagnostic evidence требует TTL. Validator также отвергает
future/naive/non-comparable timestamps и некорректное TTL-window.

## ID ownership и adapter safety

Model-facing adapter получает `tenant_id/run_id` только из trusted application
context и остаётся тонким: repositories/source ports он напрямую не импортирует.

Проверки выполняет `Scenario1ReadToolService`. До provider call он проверяет
entity **по типу** (device отдельно от site), чтобы KB/incident/switch IDs не
могли случайно стать допустимыми device/site IDs. Diagnostic разрешён только по
attachment, ранее полученному из CMDB evidence; при нескольких snapshots
используется самый новый известный.

До evidence write дополнительно проверяются provider relationships:

- CMDB device остаётся в известном site;
- site-health affected device принадлежит run;
- diagnostic target/attachment/switch/port совпадают с canonical CMDB.

Таким образом guessed/arbitrary или ID другого типа не становится authoritative
evidence только потому, что его передала модель.

## Proposal / approval / execution

Proposal states:

```text
PENDING_APPROVAL -> REJECTED | STALE | EXECUTED
```

При Approve backend делает fresh CMDB + diagnostic revalidation и проверяет:

- proposal ещё pending;
- incident OPEN;
- device всё ещё принадлежит incident;
- link всё ещё соответствует down-pattern;
- нет existing work order/equivalent executed action.

Если authoritative условие исчезло, human decision сохраняется APPROVED,
proposal -> STALE, execution = 0.

Если fresh revalidation временно невозможно из-за provider exception,
approval не потребляется: proposal остаётся PENDING_APPROVAL и возвращается
retryable typed error.

Валидный Approve создаёт ровно один ExecutedAction и один
FieldServiceWorkOrder, proposal -> EXECUTED, incident -> ESCALATED. Work-order
site/link fields берутся из trusted current CMDB.

Reject -> REJECTED, zero execution, incident остаётся OPEN.

Повтор того же human decision возвращает stored result. Repository contracts
также требуют transaction/unique constraints в будущей persistence
implementation для защиты от конкурентных duplicate requests.

## Ошибки, найденные во время ревью 3A/3B

Перед финальным PASS были исправлены несколько контрактных проблем:

- source-system ports стали run-scoped для deterministic mutable mock-world;
- удалены unsupported/invented `DeviceResolution`, work-order status и
  `guidance_code`;
- удалён generic proposal `derived_parameters` bag;
- proposal diagnostic теперь обязан быть запущен именно по canonical
  attachment;
- Phase 2 top-level diagnostic fields восстановлены в product result:
  `attachment_id`, `diagnostic`, `observed_state`;
- generic ID ownership заменён type-aware ownership для device/site;
- read/domain orchestration вынесена из adapter в application service;
- authoritative absence и temporary provider outage разделены: только первое
  ведёт к STALE; outage не потребляет approval;
- evidence `entity_ids` cross-check-ятся с typed payload;
- timestamps/TTL проходят deterministic sanity checks;
- diagnostic switch/port cross-check-ятся с CMDB до evidence write;
- provider diagnostic не вызывается, если proposal уже stale из-за incident
  state или existing action/work order;
- typed tool results получили explicit JSON-safe serialization boundary;
- добавлен architecture regression против framework imports в pure domain,
  direct port access из adapter и hardcoded canonical fixture/hidden answer.

## Tests / acceptance

Добавлен GitHub Actions workflow:
`.github/workflows/phase3-domain-check.yml`.

Финальный domain gate:

- Python 3.12;
- `compileall product_backend`;
- 3A + 3B + 3C tests;
- **67 passed**.

Полный repository regression на pinned `requirements.txt`:

- `pip check`: **No broken requirements found**;
- Python: **75 passed, 1 warning**;
- retained Node spike tests: **5 passed, 0 failed**.

Единственный Python warning — dependency deprecation в FastAPI/Starlette
TestClient surface; Phase 3 regression он не представляет.

Live Gemini повторно не запускался, потому что в Фазе 3 не менялись
`google-adk==2.10.0`, model pin или Phase 1/2 runtime agent. Live six-tool ADK
wiring ещё не входит в текущую фазу.

## Что намеренно НЕ построено

Фаза 3 не содержит:

- PostgreSQL implementation;
- product FastAPI API;
- persisted events/outbox;
- SSE;
- UI;
- auth/rate limiting;
- live six-tool ADK agent;
- Scenario 2/3 domain logic.

Это соответствует исходному roadmap: сначала устойчивый domain/contracts
foundation, затем delivery/persistence layer.

## Следующий шаг

Следующий слой можно строить поверх Phase 3 contracts:

1. PostgreSQL schema и concrete repositories/UoW;
2. persisted events/outbox;
3. product FastAPI lifecycle/approval endpoints;
4. persisted SSE;
5. UI;
6. live six-tool ADK wiring и Scenario 1 E2E acceptance.

Точный phase-number и разбиение следующего слоя следует зафиксировать до
начала реализации, чтобы снова не смешивать persistence/API/UI в один
неуправляемый шаг.


## Финальный аудит Фазы 3

После первоначального PASS выполнен отдельный полный аудит 3A+3B+3C против
canonical handoff v5.5 и Phase 2 contract.

Аудит обнаружил и устранил не косметические, а контрактные проблемы:
application/domain responsibilities больше не лежат в model-facing adapter;
`run_diagnostic` снова сохраняет обязательный Phase 2 `attachment_id`;
entity ownership стал type-aware; tool results имеют JSON-safe boundary;
evidence timestamps проходят sanity validation; approval revalidation не делает
лишние provider calls для уже stale proposal.

Также добавлен test с другим допустимым порядком read tools: success не требует
одного global walkthrough. Canonical fixture IDs и hidden
`PATCH_CABLE_DISCONNECTED` автоматически запрещены в `product_backend/`.

После этих корректировок Phase 3 остаётся **PASS**; финальный source of truth —
`PHASE_3_DOMAIN_AND_TOOL_CONTRACTS.md` и cumulative handoff v5.6.
