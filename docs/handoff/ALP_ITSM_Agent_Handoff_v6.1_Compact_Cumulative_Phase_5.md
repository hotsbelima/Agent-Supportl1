# Autonomous L1 Incident Agent

## Canonical cumulative handoff v6.1 compact — Phase 5 persisted SSE + operational UI

Дата: 5 октября 2026 года.

Этот файл — **актуальная компактная cumulative-точка входа** проекта после
полного PASS Фазы 4. Он сохраняет все решения, которые нужны следующему агенту,
но намеренно не повторяет подробные пошаговые инструкции уже закрытых фаз.
Исторические delta/checkpoint-документы остаются источником подробного trace,
если понадобится разбирать конкретную старую реализацию.

Следующий implementation stage — **Phase 5: Persisted SSE + Operational UI**.
Phase 5 подробно специфицирована ниже. Live six-tool Google ADK wiring остаётся
**Phase 6** и не должно преждевременно попадать в Phase 5.

## Как пользоваться этим handoff

При конфликте старых документов с текущим состоянием приоритет такой:

1. этот cumulative handoff v6.1;
2. текущий repository code/branch для Phase 5;
3. verified checkpoint docs Phase 4A/4B/4C и evidence Phase 4D;
4. final Phase 3 contracts;
5. исторические Phase 1/2 spike docs.

После каждой крупной фазы по-прежнему желательно иметь:

- короткий delta update с фактическими изменениями и evidence;
- новый cumulative handoff как единую точку входа.

## Краткий статус

| Фаза | Статус | Результат |
| --- | --- | --- |
| 0 | **DONE** | Архитектура, Scenario 1, fixture/world truth, evidence и approval semantics зафиксированы. |
| 1 | **DONE** | Local Google ADK/Gemini spike: dependent `get_device -> run_diagnostic` доказан 3/3. |
| 2 | **DONE** | Тот же two-tool runtime доказан на Northflank 3/3. |
| 3 | **DONE / PASS** | Product domain/contracts, validators, approval/execution boundary и six-tool adapter integration закрыты. |
| 4A | **PASS** | PostgreSQL schema/migrations, repositories/UoW, isolation, uniqueness, concurrent approval. |
| 4B | **PASS** | Persisted safe lifecycle/events/outbox, monotonic seq, UTC timestamps, audit. |
| 4C | **PASS** | Product FastAPI start/state/events/Approve/Reject, safe errors, restart/isolation. |
| 4D | **PASS** | Northflank managed PostgreSQL + product API deployment, migrations, restart/redeploy, concurrency/isolation/audit. |
| 4 | **DONE / PASS** | Persistent application backend полностью закрыт и в CI, и на managed infrastructure. |
| 5 | **NEXT** | Persisted SSE + operational UI + reconnect/state recovery + integrated delivery acceptance. |
| 6 | **PLANNED** | Live six-tool Google ADK integration + полный Scenario 1 E2E. |
| 7 | **PLANNED** | Scenario 2. |
| 8 | **PLANNED** | Scenario 3. |
| 9 | **PLANNED** | Polish/hardening/public deploy. |

## Канонический roadmap

| Фаза | Название | Верхнеуровневый результат |
| --- | --- | --- |
| **0** | Architecture / design | Архитектура, Scenario 1, fixture/world truth, evidence/approval semantics. |
| **1** | Local ADK/Gemini runtime spike | Реальный dependent multi-step tool calling локально. |
| **2** | Managed runtime spike | Тот же runtime/tool calling вне локальной машины на Northflank. |
| **3** | Product domain / contracts | Product contracts, evidence validation, ownership/state rules, approval/execution boundary, six-tool integration layer. |
| **4** | Persistence + application backend | PostgreSQL persistence, safe lifecycle/outbox, Product FastAPI и managed-infrastructure acceptance. |
| **5** | Persisted SSE + operational UI | Persisted event stream с cursor/reconnect, Next.js operational console, state recovery и integrated delivery acceptance. |
| **6** | Live six-tool Google ADK integration + Scenario 1 E2E | Все 6 Scenario 1 tools wired в ADK, полноценный vertical slice до human approval/execution. |
| **7** | Scenario 2 | Multi-event correlation, external dependency check, Major Incident flow. |
| **8** | Scenario 3 | Disconfirmed hypothesis, replanning, новая tool sequence по evidence. |
| **9** | Polish, hardening, public deploy | Security/observability hardening, UX polish, docs, architecture diagram, public demo deploy. |

Правила roadmap:

- Фазы 0–4 — baseline и не пересматриваются без технически доказанной причины.
- Phase 5 имеет точный contract в этом документе.
- Фазы 6–9 пока high-level; перед стартом каждой создаётся отдельный точный scope.
- Нельзя тащить задачи будущей фазы в текущую только потому, что они уже возможны.

## Цель продукта

Проект — демонстрационный **Autonomous L1 Incident Agent** для ITSM.
Он должен показывать не чат с зашитым ответом, а расследование:

- агент получает операционный сигнал;
- сам выбирает разрешённые read-only tools и их порядок;
- собирает evidence;
- отличает observations от hypotheses;
- при необходимости создаёт ограниченное proposal;
- execution не происходит без human approval;
- UI показывает operational facts/events, но не hidden chain-of-thought.

Целевые mock-сценарии:

1. локальная проблема терминала -> onsite Field Service proposal;
2. массовый сбой -> Major Incident proposal;
3. пересмотр неверной VPN/DNS гипотезы по новым evidence.

Реальных ServiceNow/Zabbix/CMDB/1C и реальных производственных mutations нет;
их роли воспроизводятся deterministic fixture/source-system adapters.

## Зафиксированная архитектура

```text
Next.js UI (Vercel) ── HTTPS / streaming SSE ── FastAPI (Northflank)
                                                   │
                                                   ├─ application/domain
                                                   ├─ Google ADK agent + tool adapters   [Phase 6]
                                                   ├─ PostgreSQL                         [Phase 4 DONE]
                                                   └─ deterministic simulator/fixture
```

Ключевые границы:

- modular monolith;
- один ADK agent, не multi-agent orchestrator;
- один FastAPI backend владеет product state, events, proposals и approval boundary;
- один run соответствует одной ADK session; конкурентные agent calls внутри run не нужны;
- LLM не имеет прямого доступа к БД, secrets, approval endpoint или mutation API;
- UI показывает safe facts/tool actions/findings/approval state, но не reasoning;
- SSE читает уже persisted application events, а не transient process memory.

### Разделение ответственности

| Слой | Ответственность |
| --- | --- |
| Fixture/simulator | Scenario world, initial events, hidden ground truth, deterministic observations. |
| Agent | Hypotheses, выбор tools и порядка, вывод и proposal. |
| Tool adapters | Узкий model-visible schema, delegation в application/domain path, normalized result. |
| Domain | Tenant/run/ID invariants, evidence/TTL/state transitions, duplicate/action rules. |
| Application/API | Run lifecycle, persistence, event delivery, human endpoints, idempotency. |
| Human | Approve/Reject затратного или рискованного action. |

## Runtime baseline

| Компонент | Значение |
| --- | --- |
| Python | `3.12.14` |
| Google ADK | `2.10.0` |
| Gemini | `gemini-3.5-flash-lite` |
| FastAPI | `0.141.1` |
| Uvicorn | `0.54.0` |
| pytest | `8.4.2` |
| SQLAlchemy | `2.0.54` |
| Alembic | `1.20.0` |
| psycopg | `3.3.6` |
| Managed PostgreSQL | PostgreSQL 16 |

Phase 1/2 two-tool spike остаётся историческим runtime proof и не является
product backend. Product code находится прежде всего в `product_backend/` и
`product_api/`.

## Phase 1–2: runtime proof — кратко

### Phase 1

Local ADK/Gemini spike доказал реальную цепочку:

```text
initial input: device_id = POS-KZN17-03
Gemini -> get_device(POS-KZN17-03)
result -> attachment_id = ATT-KZN17-POS03-NIC
Gemini -> run_diagnostic(ATT-KZN17-POS03-NIC)
result -> LINK_DOWN
```

`attachment_id` отсутствовал в initial input. Приложение не переносило его за
модель; dependency прошла через реальный tool result. Три независимых run — 3/3.

### Phase 2

Тот же runtime и dependent tool calling доказаны на Northflank — снова 3/3.
Credential передавался managed secret, а audit trace не содержал reasoning или
secret values.

Эти spike ID (`POS-KZN17-03`, `ATT-KZN17-POS03-NIC`) не заменяют canonical
Scenario 1 product fixture ниже.

## Canonical Scenario 1

Клиент fixture: сеть магазинов товаров для морских животных **«8 Щупалец»**.

Канонические ID:

- tenant: `TENANT-8OCT`;
- site: `SITE-KZN-017`;
- incident: `INC-1042`;
- affected terminal: `POS-KZN17-02`;
- peer terminal: `POS-KZN17-01`;
- attachment: `ATT-KZN17-POS02`;
- expected switch: `SW-KZN17-01`;
- expected port: `Gi1/0/18`.

Allowed diagnosis:

`LOCAL_ACCESS_LINK_FAILURE`

Hidden fixture truth:

`PATCH_CABLE_DISCONNECTED`

Agent **не должен** утверждать точный disconnected patch cable, пока evidence
не доказывает это. Допустимый вывод — локальная физическая проблема access path.

### Шесть product tools

1. `get_device(device_id)` — read-only;
2. `get_site_health(site_id)` — read-only;
3. `run_diagnostic(diagnostic_type, target_id)` — read-only;
4. `search_incidents(scope, entity_id)` — read-only;
5. `search_kb(query)` — read-only;
6. `propose_field_visit(...)` — только proposal; approval required.

Approve/Reject **не model tools**.

### Evidence для onsite proposal

Для `LOCAL_ACCESS_LINK_FAILURE + ONSITE_FIELD_VISIT` одновременно нужны:

1. CMDB: terminal -> attachment -> expected switch/port;
2. healthy site/payment + reachable peer + unreachable affected terminal;
3. access-link diagnostic: switch reachable, admin UP, operational DOWN,
   port security NORMAL, config EXPECTED;
4. approved KB, разрешающая onsite physical-path inspection.

Evidence immutable и typed. Dynamic `SITE_HEALTH` и
`ACCESS_LINK_DIAGNOSTIC` имеют положительный TTL. `facts`/rationale LLM сами по
себе evidence не являются.

Diagnostic можно запускать только по attachment, ранее полученному из trusted
CMDB evidence. Provider result cross-checkится с canonical topology.

### Proposal / approval semantics

`propose_field_visit` создаёт только `PENDING_APPROVAL`.

Human Approve:

- проверяет active run / open incident / ownership;
- делает fresh CMDB + diagnostic revalidation;
- provider outage -> retryable error, approval не потребляется;
- stale authoritative condition -> Approval(APPROVED), Proposal(STALE), zero execution;
- valid -> Approval + ExecutedAction + FieldServiceWorkOrder;
- proposal -> EXECUTED;
- incident -> ESCALATED;
- run -> ACTIVE.

Reject:

- Approval(REJECTED);
- proposal -> REJECTED;
- run -> ACTIVE;
- zero action/work order;
- incident остаётся OPEN.

Replay уже принятого того же human decision возвращает существующий результат
без duplicate action/work order. Конфликтующее решение после сохранённого
decision -> typed conflict.

Work order означает передачу в Field Service, а не факт ремонта. Incident не
становится RESOLVED автоматически.

## Phase 3 — product domain/contracts PASS

Phase 3 зафиксировала:

- domain entities Run/Incident/Evidence/Proposal/Approval/ExecutedAction/WorkOrder;
- typed evidence payloads;
- repository ports;
- UoW boundaries;
- deterministic proposal validation;
- human approval/revalidation semantics;
- idempotency/equivalent-action rules;
- six product tool contracts;
- separation fixture/provider truth от model-facing adapter;
- JSON-safe tool results;
- architecture tests против layer leakage.

Final Phase 3 verification:

- architecture/domain: **69 passed**;
- historical full Python at закрытии Phase 3: **77 passed**;
- Node: **5 passed**.

Phase 3 не содержала product PostgreSQL, product FastAPI/SSE/UI или live
six-tool ADK composition.

## Phase 4 — DONE / PASS

Phase 4 построила persistent application backend и доказала его сначала на
PostgreSQL CI, затем на managed Northflank.

### Phase 4A — PostgreSQL persistence PASS

Реализовано:

- PostgreSQL schema/migrations;
- async SQLAlchemy repositories;
- transactional UoWs;
- tenant/run composite ownership;
- typed Evidence JSONB mapping;
- DB uniqueness для approval/action/work-order invariants;
- row locking на proposal/approval mutation paths;
- application event/outbox tables как storage foundation.

Ключевые product tables:

- `runs`;
- `incidents`;
- `evidence`;
- `action_proposals`;
- `approvals`;
- `executed_actions`;
- `field_service_work_orders`;
- `application_events`;
- `application_outbox`.

Phase 4A PostgreSQL suite: **7 passed**.

### Phase 4B — persisted lifecycle/audit PASS

Closed event set:

- `simulation.started`;
- `external.signal`;
- `tool.started`;
- `tool.finished`;
- `finding.recorded`;
- `proposal.created`;
- `approval.decided`;
- `action.executed`;
- `run.status_changed`.

Зафиксировано:

- monotonic per-run `seq`;
- server-authoritative UTC timestamp;
- persisted safe JSON payload;
- write/read guard от hidden reasoning и credential fields;
- transactional event + outbox 1:1;
- timeline read по `after_seq`;
- replay human decision не плодит events;
- event seq allocation сериализуется owning Run lock.

Phase 4B suite: **8 passed**.

### Phase 4C — Product FastAPI PASS

Product API реализует:

- `POST /api/v1/scenario-1/runs`;
- `GET /api/v1/runs/{run_id}`;
- `GET /api/v1/runs/{run_id}/events?after_seq=...&limit=...`;
- `POST /api/v1/runs/{run_id}/proposals/{proposal_id}/approve`;
- `POST /api/v1/runs/{run_id}/proposals/{proposal_id}/reject`;
- `GET /health`.

Все product endpoints используют `X-Tenant-ID`.

Scenario 1 Start:

- создаёт persistent Run + Incident;
- сохраняет `simulation.started`;
- сохраняет `external.signal`;
- переводит CREATED -> ACTIVE;
- сохраняет `run.status_changed`;
- **не вызывает Gemini/ADK**.

State snapshot tenant/run scoped и защищён shared lock owning Run от hybrid
pre/post concurrent mutation snapshot.

HTTP errors typed/safe:

- 404 not found/context;
- 409 invalid state/proposal/evidence conflict;
- 503 upstream/database unavailable;
- generic safe 422;
- generic safe 500;
- raw exception/DSN/secrets наружу не возвращаются.

Phase 4C suite: **10 passed**.

### Phase 4D — managed Northflank acceptance PASS

Финальная branch:

`phase-4d-managed-acceptance`

Managed acceptance code SHA:

`da654020330c0bcd2fe08ee4734786fe352b293f`

Финальный branch HEAD после добавления CI trigger/check:

`9d48ed84dc844f471cf1d0838cafdfeb75c24259`

Разница между этими SHA только в GitHub Actions workflow. Product code,
`Dockerfile.product` и acceptance helpers не менялись после real Northflank
acceptance.

#### Managed resources

Northflank project:

`agent-l1-support`

Database:

- name: `DB1`;
- PostgreSQL 16;
- London;
- private networking;
- Running.

Backend:

- service: `product-api`;
- source branch: `phase-4d-managed-acceptance`;
- Dockerfile: `/Dockerfile.product`;
- `PORT=8080`;
- `DATABASE_URL` передаётся secret group;
- admin DB URI не использовался runtime service.

Важно: старый root `Dockerfile` относится к historical Phase 2 spike и запускает
`phase2_backend`. Product runtime использует отдельный `Dockerfile.product`.

#### Migration acceptance

На managed DB:

- `alembic upgrade head` — PASS;
- `alembic current` -> `20261004_0002 (head)`;
- `alembic check` — clean.

#### External product acceptance

Доказано на managed deployment:

- health + real DB reachability;
- Scenario 1 Start;
- state read;
- event timeline;
- cursor;
- Approve;
- replay Approve;
- conflicting Reject -> typed 409;
- separate Reject;
- replay Reject;
- tenant isolation;
- cross-run write isolation;
- safe typed errors.

#### Concurrent approval

Два реально параллельных Approve на fresh proposal.

Direct managed DB assertion после race:

- Approval: **1**;
- ExecutedAction: **1**;
- FieldServiceWorkOrder: **1**.

#### Lifecycle/outbox

На managed PostgreSQL доказаны:

- monotonic event sequence;
- UTC timestamps;
- safe event payloads;
- event/outbox count 1:1.

#### Persistence survival

Выполнены:

- настоящий backend restart;
- отдельный backend redeploy.

После каждого:

- health recovered;
- существующие Run A/B/C сохранились;
- approval/action/work-order state сохранился;
- timeline сохранился.

#### Secret/log audit

Не обнаружены:

- raw `DATABASE_URL`;
- DB password;
- provider credential;
- Google key;
- stack trace/secret в typed HTTP error.

### Финальный Phase 4 regression

GitHub Actions run:

`37244757105`

Result: **SUCCESS**.

На финальном SHA:

- `pip check`: PASS;
- compileall: PASS;
- Phase 4D helper imports: PASS;
- Alembic upgrade/check/downgrade/re-upgrade/check: PASS;
- Phase 3: **69 passed**;
- Phase 4A: **7 passed**;
- Phase 4B: **8 passed**;
- Phase 4C: **10 passed**;
- full Python: **102 passed, 1 external dependency warning**;
- Node: **5 passed, 0 failed**.

Единственный warning — external FastAPI/Starlette TestClient warning про
будущий переход `httpx -> httpx2`.

**Phase 4 = DONE / PASS без оговорок.**

## Source of truth после Phase 4

Для следующего этапа baseline:

- branch: `phase-4d-managed-acceptance`;
- verified final HEAD:
  `9d48ed84dc844f471cf1d0838cafdfeb75c24259`.

Фаза 5 должна начинаться от этого состояния или от новой branch, созданной
непосредственно от этого HEAD.

Не начинать Phase 5 от старой `phase-4c-product-api`.

# Phase 5 — Persisted SSE + Operational UI

## Цель

Превратить готовый persistent backend в видимый пользователю operational
product:

1. browser запускает Scenario 1;
2. получает persistent Run;
3. восстанавливает authoritative state;
4. получает safe persisted lifecycle в near-real-time;
5. показывает tools/findings/proposal/approval/action;
6. человек может Approve/Reject;
7. reload/reconnect/backend restart не уничтожают контекст;
8. PostgreSQL остаётся source of truth.

Phase 5 **не делает агента умнее и не подключает Gemini**.

В Phase 5 можно временно подготовить persisted proposal через controlled
acceptance helper/application service, чтобы проверить UI approval path.
Публичного acceptance-only endpoint для этого создавать нельзя.

## 5A — persisted SSE transport

### 5A.1 Новый endpoint

Рекомендуемый route:

`GET /api/v1/runs/{run_id}/events/stream`

Tenant context тот же, что у JSON API:

`X-Tenant-ID`

Query fallback:

`?after_seq=N`

Endpoint должен читать только persisted `application_events`.

Запрещено:

- process-memory event queue как source of truth;
- app-global subscriber state;
- Redis просто потому, что нужен SSE;
- повторная генерация lifecycle events для stream;
- отдельный «UI event model», расходящийся с 4B contract.

### 5A.2 SSE envelope

Каждый application event отправляется как нормальный SSE frame.

Пример:

```text
id: 17
event: proposal.created
data: {"event_id":"...","seq":17,"event_type":"proposal.created","occurred_at":"...","payload":{...}}

```

Правила:

- `id` = persisted per-run `seq`;
- `event` = persisted `event_type`;
- `data` = JSON serialization safe `ApplicationEvent`;
- sequence не генерируется SSE layer;
- timestamp не переписывается;
- payload не обогащается hidden runtime/model state.

Heartbeat/comment допустим, например:

```text
: keep-alive

```

Heartbeat не application event и не получает persisted seq.

### 5A.3 Cursor semantics

Поддержать оба источника cursor:

1. HTTP `Last-Event-ID`;
2. query `after_seq`.

Canonical rule:

- если корректный `Last-Event-ID` присутствует, он имеет приоритет;
- иначе использовать `after_seq`;
- default = 0;
- отрицательный/non-integer -> typed validation error.

Stream сначала отдает backlog:

`seq > cursor`

в ascending order, затем ждёт новые persisted events.

### 5A.4 Delivery semantics

Требование:

**at-least-once transport + deterministic client dedupe by seq.**

Не пытаться обещать exactly-once по network transport.

После reconnect одно и то же событие может безопасно прийти ещё раз.
UI обязан дедуплицировать по `seq`.

Gap нельзя молча игнорировать.

Если UI имеет last seq 10 и получает seq 13:

1. pause application of event 13;
2. сделать persisted backfill через JSON timeline endpoint после 10;
3. применить 11, 12, 13 по порядку;
4. продолжить stream.

### 5A.5 PostgreSQL access pattern

SSE connection **не должна** держать database transaction, session lock или
Run row lock всё время жизни HTTP connection.

Допустимый простой Phase 5 design:

1. короткий query `events after cursor`;
2. transaction/session закрыта;
3. если события есть — отправить;
4. если нет — sleep/poll interval;
5. heartbeat по отдельному timer;
6. следующий короткий query.

Никакого LISTEN/NOTIFY/Redis сейчас не требуется, если polling удовлетворяет
demo latency.

Suggested poll interval: приблизительно 0.5–1.0 s.

Не фиксировать эту цифру как domain contract, если implementation test
показывает разумный near-real-time UX.

### 5A.6 Disconnect

При disconnect:

- coroutine прекращает polling;
- DB session не остаётся висеть;
- нет background task leak;
- reconnect использует persisted cursor.

### 5A.7 CORS

Frontend планируется на Vercel, backend — Northflank.

FastAPI должен иметь explicit CORS allowlist.

Не использовать без необходимости:

`allow_origins=["*"]`

при credential-like/trusted application context.

Минимум предусмотреть configured frontend origin env, например:

`FRONTEND_ORIGIN`

Если нужен preview origin strategy, она должна быть явной и безопасной, а не
случайным wildcard.

### 5A.8 Tenant header и browser transport

Текущий API требует `X-Tenant-ID`.

Native browser `EventSource` не позволяет задать произвольный
`X-Tenant-ID` header.

Поэтому Phase 5 не должна ради UI ломать tenant boundary.

Recommended solution:

**streaming `fetch()` + SSE parser в frontend.**

То есть:

```text
fetch(streamUrl, {
  headers: {
    "X-Tenant-ID": tenantId,
    "Last-Event-ID": String(lastSeq)
  }
})
```

и streaming parsing `text/event-stream`.

Альтернативный same-origin BFF proxy допустим только если он действительно
упрощает architecture и не хранит лишний state. По умолчанию direct
streaming fetch проще.

Не переносить tenant ID в insecure global query только ради native EventSource.

## 5B — Next.js operational UI

### 5B.1 Frontend stack

Новый frontend:

- Next.js;
- TypeScript;
- отдельный package boundary;
- deploy на Vercel.

Не смешивать UI files с historical `public/` Phase 2 spike.

Не требуется сложная design system.

Цель — чистая operational console, белый фон, понятная auditability.

### 5B.2 Минимальные routes

Рекомендуется:

`/`

Start/landing screen.

`/runs/[runId]`

Run console.

Deep link на run должен работать после browser reload.

### 5B.3 Start screen

Показывать:

- продукт/Scenario 1;
- fixture client «8 Щупалец»;
- краткий текст инцидента;
- кнопку **Start simulation**.

По клику:

`POST /api/v1/scenario-1/runs`

с `X-Tenant-ID: TENANT-8OCT`.

После 201:

- получить run ID;
- navigate `/runs/{run_id}`;
- больше не хранить состояние только в memory component.

Double click:

- button disabled во время request;
- не должно создавать случайно два visible active runs из одного UI action.

Phase 5 не обязана вводить глобальную business-idempotency start key, если
такого contract не было в Phase 4. UI-level protection достаточно, если это
явно зафиксировано.

### 5B.4 Run bootstrap

При открытии `/runs/[runId]`:

1. GET authoritative state;
2. GET persisted events backlog или использовать state.latest_event_seq;
3. построить UI;
4. открыть SSE stream от известного cursor.

Не начинать с пустого UI, надеясь, что SSE заново пришлёт всю историю.

State endpoint — authoritative current state.
Events — authoritative timeline.

### 5B.5 Экран Run

Минимум следующие зоны.

#### Header

- Scenario 1;
- Run ID;
- connection state;
- run status.

Connection states:

- Connecting;
- Live;
- Reconnecting;
- Unavailable.

#### Incident panel

- Incident ID;
- site;
- affected device;
- symptom;
- incident status.

#### Timeline

Показывает persisted events по ascending `seq`.

Не raw JSON dump.

Визуально различать хотя бы:

- external signal;
- tool activity;
- finding;
- proposal;
- human decision;
- action;
- run status change.

Timeline должен использовать безопасные event payloads, уже прошедшие 4B guard.

#### Evidence / findings

Показывать operational evidence отдельно от «мысли агента».

Для каждого evidence достаточно:

- source type;
- entity IDs;
- safe observation summary/structured facts;
- freshness, если dynamic.

Не показывать hidden diagnosis truth.

#### Proposal / Approval card

Если есть `PENDING_APPROVAL`:

- action: onsite field visit;
- incident/device;
- diagnosis;
- evidence references;
- rationale;
- Approve;
- Reject.

Во время decision request обе кнопки disabled.

После outcome card показывает authoritative stored status.

#### Action / Work order

После valid Approve:

- proposal EXECUTED;
- work order created;
- incident ESCALATED;
- safe routing/location fields.

Нельзя показывать:

- repaired;
- resolved;
- terminal fixed;

если backend этого не доказал.

### 5B.6 Human decision

Approve:

`POST /api/v1/runs/{run_id}/proposals/{proposal_id}/approve`

Reject:

`POST /api/v1/runs/{run_id}/proposals/{proposal_id}/reject`

UI не реализует свои domain rules.

После response:

- немедленно принять returned authoritative result;
- затем timeline/SSE дополнит UI persisted events.

Если network response потерян после server commit:

- UI делает state refresh;
- backend replay/idempotency Phase 4 защищает повтор;
- UI не должен создавать optimistic fake action.

### 5B.7 Typed errors

UI должен понимать generic error envelope backend.

Минимум:

- 404 -> run/proposal not found;
- 409 -> conflict/current state changed;
- 422 -> invalid request;
- 503 -> backend/database dependency unavailable;
- 500 -> internal error, без показа raw stack.

Не выводить `response.text()` целиком пользователю как error details.

## 5C — reconnect / state recovery

Это отдельный checkpoint, а не «полировка».

### 5C.1 Browser reload

После F5 на `/runs/{run_id}`:

- run ID берётся из URL;
- tenant context восстанавливается из explicit demo config;
- state перечитывается;
- timeline перечитывается/reconciles;
- SSE стартует после recovered cursor.

React in-memory state не должен быть source of truth.

### 5C.2 Cursor storage

Минимально cursor живёт в runtime state и восстанавливается из persisted
timeline/state после reload.

Можно дополнительно сохранить last processed seq в `sessionStorage`, но это
только optimization. Нельзя доверять ему больше backend.

### 5C.3 Dedupe

Client держит `lastAppliedSeq`/indexed event map.

Event с уже применённым seq:

- не создаёт вторую timeline row;
- не повторяет notification;
- не повторяет local derived state transition.

### 5C.4 Gap recovery

Если следующий seq не `last + 1`:

- не продолжать молча;
- JSON backfill;
- verify contiguous ordering;
- затем resume.

Если backfill не восстанавливает gap:

- connection state -> Unavailable/degraded;
- показать safe error;
- retry state/timeline bootstrap.

### 5C.5 Reconnect policy

При network disconnect:

- connection state -> Reconnecting;
- exponential backoff с разумным cap;
- reconnect с cursor;
- не открывать бесконтрольно несколько streams.

При successful frame/heartbeat:

- state -> Live.

### 5C.6 Backend restart

Настоящий Northflank restart должен выглядеть так:

1. SSE disconnect;
2. UI Reconnecting;
3. product-api возвращается;
4. state/backfill доступен;
5. stream продолжает с последнего seq;
6. existing Run/Incident/Proposal/Approval state не теряется.

Это must-pass acceptance.

## 5D — integrated delivery acceptance

### 5D.1 Deploy topology

Использовать:

- Vercel — Next.js frontend;
- Northflank — existing `product-api`;
- Northflank `DB1` — existing PostgreSQL 16.

Не создавать вторую DB ради UI.

### 5D.2 Northflank

Phase 5 может добавить SSE/CORS runtime изменения в `product-api`.

После deploy:

- migrations не должны неожиданно менять schema, если Phase 5 schema change не нужен;
- `alembic check` clean;
- `/health` green;
- existing Phase 4 data readable.

### 5D.3 Vercel env

Frontend получает только public-safe configuration:

например:

- public backend base URL;
- demo tenant ID, если он считается fixture UI context.

Frontend **не получает**:

- DATABASE_URL;
- DB credentials;
- GOOGLE_API_KEY;
- provider secrets.

Если env доступна browser bundle, считать её public.

### 5D.4 Proposal для pre-ADK UI acceptance

Проблема ожидаемая: до Phase 6 Start не запускает agent и сам не создаёт
proposal.

Для acceptance Proposal UI использовать controlled method:

- существующий non-public `scripts/phase4d_seed_proposal.py`, если он
  по-прежнему совместим;
- либо equivalent internal acceptance script/job через application service.

Не создавать:

- `POST /test/create-proposal`;
- `/debug/seed`;
- frontend-only fake proposal;
- direct raw SQL insert.

Controlled seed должен пройти существующую domain/application validation.

### 5D.5 End-to-end acceptance

Минимальный реальный сценарий:

1. открыть Vercel URL;
2. Start simulation;
3. получить run route;
4. state показывает ACTIVE Run + OPEN incident;
5. timeline показывает initial three persisted events;
6. открыть stream;
7. controlled job создаёт valid pending field-visit proposal;
8. UI без reload получает lifecycle events и показывает proposal;
9. evidence/proposal данные соответствуют backend;
10. нажать Approve;
11. UI показывает persisted Approval/Action/WorkOrder;
12. incident ESCALATED;
13. reload page;
14. UI показывает тот же authoritative state;
15. timeline получает approval/action/status events;
16. reload сохраняет тот же result;
17. повторный Approve/retry не создаёт второй work order;
18. повторить на отдельном run для Reject path;
19. выполнить настоящий Northflank backend restart при открытом UI;
20. UI переходит в reconnect и затем возвращается в Live;
21. timeline после reconnect без gap/duplicate;
22. данные после restart сохранены;
23. browser console не содержит raw secrets/DSN;
24. backend logs не содержат raw secrets;
25. публичный frontend bundle не содержит backend secret env.

### Phase 5 automated tests

#### Backend

Сохранить все Phase 3/4 regression.

Добавить dedicated Phase 5 SSE tests:

- cursor;
- replay;
- reconnect;
- new-event delivery;
- tenant/run isolation;
- safe payload;
- heartbeat;
- disconnect cleanup;
- no long transaction blocking writer.

#### Frontend unit/component

Минимум:

- API error normalization;
- SSE frame parser;
- dedupe по seq;
- gap detection;
- timeline reducer;
- connection state transitions;
- proposal button state;
- status presentation;
- no `RESOLVED` assumption.

#### Browser E2E

Рекомендуется Playwright.

Хотя бы один E2E должен запускать реальный frontend + backend + PostgreSQL,
а не полностью mocked API.

Проверить:

- Start;
- route/deep link;
- timeline bootstrap;
- live event;
- proposal appearance;
- Approve;
- reload recovery;
- reconnect recovery.

CI setup может создавать pending proposal через controlled test fixture/
application service. Не добавлять для Playwright специальный production
endpoint.

### Full regression после Phase 5

Финальный Phase 5 gate должен включать:

- `pip check`;
- Python compileall;
- Alembic check;
- Phase 3 regression;
- Phase 4A regression;
- Phase 4B regression;
- Phase 4C regression;
- новые Phase 5 backend tests;
- полный Python regression;
- retained historical Node regression;
- frontend install from lockfile;
- frontend typecheck;
- frontend lint;
- frontend unit/component tests;
- frontend production build;
- browser E2E.

Не объявлять PASS только потому, что `next build` успешен.

## PASS criteria Phase 5

Phase 5 считается PASS только если одновременно доказано:

1. SSE читает **persisted** application events, а не process-memory queue;
2. каждый persisted event передаётся с `id == seq`;
3. reconnect продолжает с persisted cursor;
4. reload восстанавливает state/timeline из backend;
5. gap detection/backfill работает;
6. duplicate/replayed events не создают duplicate UI rows;
7. SSE connection не держит долгую DB transaction/Run lock;
8. cross-tenant/cross-run event leakage отсутствует;
9. UI Start создаёт настоящий persistent Scenario 1 run;
10. UI отображает authoritative Run/Incident state;
11. UI отображает persisted timeline;
12. proposal card отображается только при реальном persisted proposal;
13. Approve/Reject идут через существующие Phase 4 endpoints;
14. repeat/retry decision остаётся idempotent;
15. WorkOrder не отображается как repair/RESOLVED;
16. browser reload после Approve сохраняет result;
17. настоящий backend restart приводит к reconnect, а не потере run;
18. Vercel frontend и Northflank backend реально работают вместе;
19. secrets/DSN/API keys отсутствуют в browser bundle, responses и logs;
20. UI не показывает hidden reasoning/chain-of-thought;
21. все Phase 3/4 regression остаются зелёными;
22. frontend type/build/tests/E2E зелёные;
23. Phase 6 ADK/Gemini wiring не было незаметно протащено в Phase 5.

Если хоть один обязательный пункт не доказан — Phase 5 не PASS.

## Hard FAIL Phase 5

Сначала исправить причину, если:

- timeline строится из in-memory queue и исчезает после restart;
- SSE reconnect начинается с нуля и плодит duplicate rows;
- gap sequence silently игнорируется;
- browser tenant context передаётся обходным небезопасным способом только ради
  EventSource;
- SSE держит PostgreSQL transaction/lock минуты;
- UI читает PostgreSQL напрямую;
- frontend получает `DATABASE_URL`/DB password/Google key;
- public test endpoint создаёт proposal только ради UI demo;
- proposal/action/work order рисуются без persisted backend state;
- UI заявляет `RESOLVED` после одного work order;
- hidden CoT/reasoning выводится в timeline;
- backend error/DSN попадает в browser;
- Phase 5 начинает вызывать Gemini;
- создаётся hard-coded agent-like sequence вместо Phase 6;
- старые Phase 3/4 tests становятся красными и это «игнорируется».

## Physical deliverables Phase 5

После PASS должны физически существовать:

### Backend

- persisted SSE route;
- CORS config;
- SSE integration tests;
- reconnect/cursor contract documentation.

### Frontend

- отдельный Next.js/TypeScript app;
- Start page;
- `/runs/[runId]` operational console;
- Run/Incident panel;
- timeline;
- Evidence panel;
- Proposal/Approval controls;
- Action/WorkOrder state;
- connection/reconnect state;
- API/SSE client;
- tests;
- production build.

### Infrastructure

- updated Northflank `product-api`;
- existing DB1 reused;
- Vercel frontend deployment;
- documented frontend/backend URLs/config;
- external integrated acceptance evidence.

### Documentation

После PASS Phase 5:

- Phase 5 delta update;
- новый cumulative handoff для Phase 6.

## Что будет делать Phase 6 — чтобы не смешать границы

Phase 6 = **Live six-tool Google ADK integration + Scenario 1 E2E**.

Там уже понадобится настоящий agent runtime.

В Phase 6:

- создаётся production ADK composition;
- один Run связывается с одной ADK session;
- все шесть Scenario 1 tools подключаются к Google ADK;
- Gemini сама выбирает tool order;
- аргументы следующих tools должны реально зависеть от предыдущих results;
- agent собирает evidence через existing application services;
- agent вызывает `propose_field_visit`;
- proposal останавливается на human approval;
- human Approve/Reject остаётся application operation, не model tool;
- фактический approval result возвращается в ту же ADK session;
- agent завершает ответ честно, без объявления repair/RESOLVED;
- весь flow виден в UI Phase 5 через persisted events.

Именно поэтому в Phase 5 нельзя делать «временного AI» или scripted imitation
agent behavior.

## Рекомендуемая последовательность реализации Phase 5

Не делать всю фазу одним огромным commit.

### 5A

Сначала:

- SSE backend;
- cursor/reconnect contract;
- PostgreSQL streaming tests;
- CORS.

Checkpoint result:

**backend умеет безопасно stream persisted timeline**.

### 5B

Затем:

- frontend package;
- Start;
- run route;
- state/timeline/evidence/proposal UI;
- Approve/Reject.

Checkpoint result:

**operational console работает поверх обычных JSON endpoints и SSE**.

### 5C

Затем:

- reload bootstrap;
- cursor persistence;
- dedupe;
- gap recovery;
- reconnect;
- unavailable states.

Checkpoint result:

**browser/backend restart не ломают operational state**.

### 5D

Финально:

- Vercel deploy;
- Northflank Phase 5 redeploy;
- real external integration;
- controlled proposal setup;
- UI approval flow;
- restart/reconnect proof;
- full regression.

Checkpoint result:

**Phase 5 DONE/PASS**.


## Быстрая проверка repository

Для обычного local/CI regression:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
npm test
```

Phase 4 PostgreSQL integration tests требуют настоящий PostgreSQL и
`DATABASE_URL`; canonical GitHub workflows поднимают PostgreSQL 16 service
container. Live Gemini для 4A–4D regression не нужен.

Исторический Phase 1 live runner по-прежнему запускается отдельно:

```powershell
.\.venv\Scripts\python.exe -m phase1_adk_spike.runner --runs 3
```

Для него нужен `GOOGLE_API_KEY` в ignored `.env`. Не смешивать этот live spike
с 4D product backend acceptance.

Product API runtime:

```bash
python -m product_api
```

Product migrations:

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

## Передача агенту Phase 5

Использовать **этот cumulative handoff v6.1** как основную точку входа.

Стартовая инструкция агенту:

> Фазы 0–4 закрыты. Phase 4 полностью PASS и доказана как в PostgreSQL/FastAPI
> CI, так и на managed Northflank infrastructure. Начни Phase 5 строго от
> `phase-4d-managed-acceptance` verified HEAD
> `9d48ed84dc844f471cf1d0838cafdfeb75c24259`.
> Не пересматривай Phase 3 domain contracts, Phase 4 persistence/event/approval
> semantics и не подключай Google ADK/Gemini. Реализуй 5A persisted SSE,
> 5B Next.js operational UI, 5C reconnect/state recovery и 5D integrated
> Vercel/Northflank acceptance по точному contract этого документа.
> Browser SSE client должен сохранить `X-Tenant-ID`; поэтому используй
> streaming fetch, а не ломай tenant boundary ради native EventSource.
> PostgreSQL остаётся единственным source of truth для application events.
> Не добавляй public test/proposal endpoint: для pre-Phase-6 approval UI
> acceptance используй controlled fixture/application service/managed job.
> PASS объявляй только после полного backend/frontend/E2E regression и реального
> reconnect/reload/restart proof.

Агент не должен задавать повторные вопросы о Scenario 1 IDs, Phase 4 resource
names, runtime pins, approval semantics или roadmap: всё это зафиксировано выше.

Если Phase 5 вскрывает техническую проблему в Phase 4, сначала доказать её
воспроизводимым test, сделать минимальный fix и прогнать полный regression.
Нельзя менять domain semantics только потому, что UI так удобнее.

После Phase 5 агент обязан вернуть:

- exact final commit;
- список backend/frontend files;
- SSE route contract;
- frontend deployment URL;
- Northflank deployment identity;
- CORS configuration без secret values;
- automated test counts;
- real UI Start/run/reload evidence;
- live proposal/Approve/Reject acceptance evidence;
- backend restart/reconnect evidence;
- security/log/browser audit;
- final PASS/PARTIAL status.

После PASS Phase 5 выпустить новый cumulative handoff для Phase 6.
