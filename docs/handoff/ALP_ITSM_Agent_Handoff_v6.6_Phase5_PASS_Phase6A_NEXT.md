# Autonomous L1 Incident Agent

## Canonical cumulative handoff v6.6 — Phase 5 PASS; Phase 6A NEXT; Phase 6 boundary preserved

Дата: 5 октября 2026 года.

Этот файл — **актуальная compact cumulative-точка входа** проекта после полного
**Phase 5 DONE / PASS**. Он создан **на базе handoff v6.5**, а не v6.2: весь
boundary-аудит Phase 6 (`ADK owns / Product owns`) и целевая native-ADK
архитектура v6.5 сохранены как канонические.

Документ намеренно:
- фиксирует фактическое завершение **5C + 5D1 + 5D2** и evidence managed acceptance;
- заменяет устаревшие инструкции «5C NEXT / D1 PLANNED / D2 PLANNED» на фактический результат;
- сохраняет Phase 3/4/5 product/domain boundaries;
- сохраняет без архитектурного отката ownership boundary **ADK owns / Product owns** из v6.5;
- требует начать Phase 6 строго с **6A architecture correction / Phase 4B pruning**, а не наслаивать live ADK поверх legacy runtime plumbing;
- фиксирует известный визуальный долг UI, чтобы требование снова не потерялось между handoff-версиями.

Текущая точка остановки:

> **Phase 5 = DONE / PASS. Phase 6A = NEXT.**

Канонический baseline для следующей работы:

- repository: `hotsbelima/Agent-Supportl1`;
- managed-accepted code commit: `47be2321787fa4903702ba38f9c50838e1498033`;
- D1 branch: `phase-5d1-isolated-verification`;
- D2 deployment/acceptance branch: `phase-5d2-managed-acceptance`;
- D2 не меняла product code относительно D1 release candidate;
- следующую development branch создать **от exact commit `47be232...`**.

---

## Как пользоваться этим handoff

При конфликте информации приоритет:

1. этот cumulative handoff v6.6;
2. repository code на managed-accepted commit `47be2321787fa4903702ba38f9c50838e1498033`;
3. handoff v6.5 для Phase 6 boundary history/audit rationale;
4. Phase 5 checkpoint evidence и D2 managed acceptance report;
5. Phase 4 verified evidence;
6. Phase 3 contracts;
7. исторические Phase 1/2 spike docs.

Следующий исполнитель **не должен заново проектировать Phase 0–5**.
Если текущий code contradicts этому handoff, сначала воспроизвести проблему test'ом.

После major checkpoint по-прежнему:
- фиксировать exact final commit;
- фиксировать CI/evidence;
- не объявлять PASS без выполнения checkpoint criteria;
- ownership boundary Phase 6 не пересматривать без конкретного воспроизводимого дефекта или проверенного ограничения ADK.

---

## Краткий статус

| Фаза | Статус | Результат |
| --- | --- | --- |
| 0 | **DONE** | Architecture, Scenario 1, fixture/world truth, evidence/approval semantics. |
| 1 | **DONE** | Local Google ADK/Gemini dependent two-tool runtime 3/3. |
| 2 | **DONE** | Тот же runtime на Northflank 3/3. |
| 3 | **DONE / PASS** | Domain/contracts, validators, evidence, approval/execution boundary, six-tool adapter layer. |
| 4 | **DONE / PASS** | PostgreSQL persistence + persisted lifecycle/events + Product API + managed Northflank acceptance. |
| 5A | **DONE / PASS** | Persisted SSE transport + cursor + heartbeat + CORS + PostgreSQL streaming tests. |
| 5B | **DONE / PASS** | Next.js operational UI + Start/run route + timeline/evidence/proposal/approval/work-order UI. |
| 5C | **DONE / PASS** | Reload bootstrap, per-run cursor, dedupe, gap/backfill recovery, reconnect/backoff, lost-decision recovery. |
| 5D1 | **DONE / PASS** | Isolated release verification, controlled proposal acceptance, source/bundle security audit, Docker build. |
| 5D2 | **DONE / PASS** | Vercel + Northflank + DB1 managed acceptance, real browser flow, Approve/Reject, real backend restart/reconnect. |
| 5 | **DONE / PASS** | Full frontend/backend/persistence/recovery managed acceptance completed. |
| 6A | **NEXT** | Architecture correction / Phase 4B pruning → native ADK runtime ownership. |
| 6B–6D | **PLANNED** | Native six-tool Google ADK wiring → human decision/resume → full Scenario 1 E2E. |
| 7 | **PLANNED** | Scenario 2. |
| 8 | **PLANNED** | Scenario 3. |
| 9 | **PLANNED** | Polish/hardening/public deploy. |

### Known UI visual requirement — do not lose again

Пользователь ранее задавал требование **light/white UI**. В промежуточном cumulative
handoff оно было потеряно, и Phase 5 functional acceptance прошёл на текущем dark UI.
Это не переоткрывает Phase 5 по решению пользователя, но остаётся **явным визуальным долгом**:
- не удалять это требование из следующих handoff;
- при ближайшем целевом frontend polish вернуть light/white visual treatment;
- крайний срок — Phase 9 polish/public deploy, если пользователь не попросит раньше.

---

## Цель продукта

Проект — демонстрационный **Autonomous L1 Incident Agent** для ITSM.

Он должен показывать практический опыт создания реально действующего агента:
tool calling, state, actions, guardrails, approvals, event-driven поведение
и понятный бизнес-кейс.

Целевой продукт:
- получает operational signal;
- агент сам выбирает разрешённые read-only tools и порядок;
- собирает typed evidence;
- отличает observations от hypotheses;
- создаёт constrained proposal;
- execution идёт только после human approval;
- UI показывает safe operational facts/events, но не hidden chain-of-thought.

Mock scenarios:
1. локальная проблема терминала → onsite Field Service proposal;
2. массовый сбой → Major Incident proposal;
3. пересмотр неверной VPN/DNS hypothesis по evidence.

Реальных production ServiceNow/Zabbix/CMDB/1C mutations нет.
Используются deterministic fixture/source-system adapters.

---

## Каноническая архитектура

После Phase 5:

```text
Next.js operational UI (Vercel)
          │
          ├── HTTPS JSON API
          └── HTTPS persisted SSE
                    │
                    ▼
FastAPI product_api (Northflank)
          │
          ├── application/domain
          ├── persisted business/operational application_events
          ├── approval/execution services
          └── PostgreSQL 16 (Northflank DB1)
```

Phase 6 добавляет ADK как **agent runtime**, а не как второй product backend и не как слой,
который надо заново реализовать внутри проекта:

```text
                 Google ADK / Gemini
      Runner · Session · Events · tools · resume
                       │
                thin integration layer
                       │
                       ▼
Next.js UI ──► FastAPI Product API ──► application/domain
                    │                        │
                    │                        ├─ Incident / Evidence
                    │                        ├─ Proposal / Approval
                    │                        ├─ ExecutedAction / WorkOrder
                    │                        └─ business idempotency
                    │
                    ├─ Product application_events ──► persisted SSE ──► UI
                    │
                    └─ PostgreSQL 16
                         ├─ Product-owned tables
                         └─ ADK-owned session/event/state tables
```

### Ownership boundary Phase 6

#### ADK owns

- agent loop / `Runner` execution lifecycle;
- ADK `Session` и runtime/session state;
- runtime `Event` history, function calls и function responses;
- persistent agent sessions/events/state через `DatabaseSessionService`;
- generic tool invocation plumbing через ADK tools/`ToolContext`;
- invocation pause/resume и long-running tool mechanics;
- generic agent-level retry/recovery **mechanism and execution lifecycle** через ADK plugin system (например, `ReflectAndRetryToolPlugin`) там, где модели действительно нужно повторить/исправить tool call; конкретная policy того, какие Product failures считаются retryable, остаётся Product-owned;
- callback/plugin lifecycle и invocation hooks как framework mechanism; custom business/security policy, реализованная через эти hooks, остаётся Product-owned;
- runtime tracing/OpenTelemetry instrumentation mechanism; exporter/config и дополнительные Product/domain spans могут настраиваться приложением;
- generic agent-runtime bookkeeping, которое не является business truth.

#### Product owns

- `Run`, `Incident`, `Evidence`, `ActionProposal`, `Approval`, `ExecutedAction`, `FieldServiceWorkOrder`;
- source-system adapters и реальные implementation bodies шести product tools;
- model-facing safe Product tool contracts: typed success/failure results, redaction/sanitization и domain validation; ADK вызывает tool, но не определяет нашу business/error semantics;
- transport/provider retry/backoff внутри source-system adapters, когда повтор того же сетевого вызова технически безопасен и не требует нового решения модели;
- конкретная business/security/authorization policy и guardrail rules; ADK callbacks/plugins могут быть механизмом enforcement, но содержание policy принадлежит Product;
- tenant/run ownership и isolation;
- evidence provenance, TTL, topology/currentness validation;
- proposal constraints и business state transitions;
- Approve/Reject HTTP application operations и audit human actor;
- business idempotency / защита от duplicate side effects;
- business/operational audit: proposal/approval/action/status/finding events;
- Product API, persisted `application_events`, Product SSE и operational UI;
- safe **allowlisted** projection runtime activity в Product timeline, если она нужна UI; raw ADK Event/prompt/model internals целиком в Product audit не копировать;
- durable correlation/dispatch bridge между Product decision и ADK resume (минимальные `session_id` / `invocation_id` / function-call references и, если нужен reliable async delivery, Product outbox/worker);
- portable domain/tool **service contracts**. HTTP — только один возможный adapter для Dify/внешнего orchestrator; внутри текущего modular monolith ADK не обязан ходить к собственному Product backend через сеть.

### Что **не** означает portability

Возможность позже заменить ADK другим orchestrator (включая Dify) обеспечивается тем,
что product/domain/services/tools не принадлежат ADK. Она **не требует** собственного
аналога ADK Session/Events/retry/resume/tracing. При смене framework допускается заменить
framework-specific execution state; business state и tool implementations должны сохраниться.

### Неподвижные границы

- modular monolith;
- один ADK agent, не multi-agent orchestrator;
- один FastAPI владеет product state/business audit/proposals/approval;
- один Run ↔ одна ADK session в Phase 6;
- LLM не получает прямой DB/secrets/approval endpoint/mutation access;
- Product PostgreSQL tables — source of truth для business/product state;
- ADK `DatabaseSessionService` — source of truth для agent runtime session/events/state;
- ADK-owned tables не превращать в Product Alembic/domain schema;
- browser/React state не authoritative;
- Product SSE продолжает читать persisted `application_events`, не process memory и не raw hidden ADK internals;
- UI не показывает hidden reasoning;
- Approve/Reject — application operations, не model tools;
- ADK отвечает за runtime pause/resume semantics вокруг human decision; Product/integration layer отвечает за durable correlation и доставку уже принятого business decision в ADK resume; Product — за сам decision и side effects;
- WorkOrder не означает repair и не переводит incident в `RESOLVED`;
- Phase 5 не вызывает Gemini и не имитирует будущего агента.

---

## Runtime baseline

Backend:
- Python `3.12.14`;
- Google ADK `2.10.0` — пока только historical spike;
- Gemini `gemini-3.5-flash-lite` — live product wiring только Phase 6;
- FastAPI `0.141.1`;
- Uvicorn `0.54.0`;
- pytest `8.4.2`;
- SQLAlchemy `2.0.54`;
- Alembic `1.20.0`;
- psycopg `3.3.6`;
- PostgreSQL `16`.

### ADK 2.10.0 capability check for Phase 6 boundary

Ownership выше сверялся именно с pinned Python `google-adk==2.10.0`, а не только с более новой документацией. В этой версии уже присутствуют нужные framework primitives: `Runner`, persistent `DatabaseSessionService` с SQLAlchemy `AsyncEngine`, `Session.state`/persisted Events, `FunctionTool`/`ToolContext`, `LongRunningFunctionTool`, `ResumabilityConfig`, `ReflectAndRetryToolPlugin`, callback/plugin lifecycle и OpenTelemetry tracing support. Поэтому для этих generic runtime responsibilities свой framework не нужен. При этом ADK не знает Product semantics: Incident/Evidence/Proposal/Approval, business idempotency, authorization policy, safe Product error contract и durable delivery business decision → resume остаются application/integration responsibilities.

Frontend checkpoint 5B:
- Next.js `16.3.8`;
- React `19.3.0`;
- TypeScript `6.0.3`;
- ESLint `9.39.1`;
- Vitest `5.0.3`;
- Node 22 в canonical CI;
- отдельный `frontend/` package с committed `package-lock.json`.

---

## Canonical Scenario 1

Клиент: сеть магазинов товаров для морских животных **«8 Щупалец»**.

IDs:
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

Agent не должен утверждать точный disconnected patch cable без evidence.
Допустимый вывод — локальная физическая проблема access path.

### Шесть product tools Phase 6

1. `get_device(device_id)`
2. `get_site_health(site_id)`
3. `run_diagnostic(diagnostic_type, target_id)`
4. `search_incidents(scope, entity_id)`
5. `search_kb(query)`
6. `propose_field_visit(...)`

Approve/Reject не являются model tools.

### Evidence для onsite proposal

Нужны одновременно:
1. CMDB topology terminal → attachment → expected switch/port;
2. healthy site/payment + reachable peer + unreachable affected terminal;
3. diagnostic: switch reachable, admin UP, oper DOWN, security NORMAL, config EXPECTED;
4. approved KB для onsite physical-path inspection.

`facts` и rationale сами по себе evidence не являются.
Dynamic site health/diagnostic имеют положительный TTL.
Diagnostic target должен происходить из trusted CMDB evidence.

### Approval semantics

`propose_field_visit` создаёт только `PENDING_APPROVAL`.

Approve:
- ownership/state checks;
- fresh CMDB + diagnostic revalidation;
- upstream outage → retryable error, approval не consumed;
- stale → Approval(APPROVED) + proposal STALE + zero execution;
- valid → ровно 1 ExecutedAction + 1 FieldServiceWorkOrder,
  proposal EXECUTED, incident ESCALATED, run ACTIVE;
- replay same decision возвращает stored result;
- conflicting post-commit decision не выполняется.

Reject:
- Approval(REJECTED);
- proposal REJECTED;
- run ACTIVE;
- incident OPEN;
- zero action/work order.

---

## Phase 3–4 — закрытый baseline

### Phase 3 — DONE / PASS

Созданы:
- `product_backend/`;
- domain entities/enums/errors/transitions;
- repositories/UoW/source-system ports;
- typed Evidence;
- deterministic proposal validator;
- approval/execution service;
- stale/replay semantics;
- six Scenario 1 tool contracts;
- `DefaultScenario1ToolAdapter`;
- ownership/topology validation;
- safe typed errors.

Live Gemini product flow намеренно отсутствовал.

### Phase 4 — DONE / PASS

Закрыты:
- PostgreSQL/Alembic schema;
- repositories/UoW;
- tenant/run isolation;
- DB uniqueness/concurrency;
- persisted safe lifecycle/events/outbox;
- monotonic per-run seq + UTC timestamps;
- Product FastAPI start/state/timeline/Approve/Reject;
- safe error boundary;
- Northflank managed PostgreSQL/product-api acceptance;
- restart/redeploy persistence proof.

### Phase 4B architectural note for Phase 6

Phase 4 остаётся **PASS для своего checkpoint**. Перед Phase 6 не переписывать его посреди
5C/5D. Но review после 5B установил, что в 4B вместе с полезным business audit был создан
лишний generic agent-runtime plumbing.

**Оставить как Product-owned:**
- `proposal.created`;
- `approval.decided`;
- `action.executed`;
- `run.status_changed`;
- `finding.recorded` и другие safe business/operational facts;
- per-run business timeline, seq, tenant isolation;
- DB constraints/idempotency/business audit.

**В Phase 6 пересмотреть/убрать как дублирование ADK:**
- ручное использование `tool.started` / `tool.finished` как собственного execution lifecycle;
- runtime-audit responsibilities в `DefaultScenario1ToolAdapter` (`_record_started`, manual finish bookkeeping и аналогичный generic plumbing);
- попытки хранить agent execution state отдельно от ADK Session;
- будущие самописные generic retry/pause/resume/tracing mechanisms;
- `application_outbox` **не объявлять лишним заранее**. В 6A сначала проверить, нужен ли он как durable delivery path для `approval committed → resume ADK invocation` или другого реального Product event consumer. Если такой consumer появляется — оставить и использовать по назначению. Только если после проектирования 6C реального consumer/use case нет — deprecate; физическое удаление только forward Alembic migration, уже применённые Phase 4 migrations не редактировать.

Если UI по-прежнему нужен `tool.started/tool.finished`, event types можно сохранить как
**safe projection из ADK runtime events в Product `application_events`**. Их source of truth
тогда ADK runtime, а Product timeline — presentation/audit projection, не второй execution engine.

Managed baseline:
- project: `agent-l1-support`;
- DB: `DB1`, PostgreSQL 16, London, private networking;
- service: `product-api`;
- port: `8080`;
- `DATABASE_URL` из managed secret group;
- `Dockerfile.product`;
- migration head: `20261004_0002 (head)`.

Final Phase 4 verified HEAD:
`9d48ed84dc844f471cf1d0838cafdfeb75c24259`.

---

# Phase 5A — DONE / PASS

Branch:

`phase-5a-persisted-sse`

Final verified HEAD:

`ceb290f54cc144caaaeb71ab084bdb6b86158b0b`

Final GitHub Actions:

`37248399767` — **SUCCESS**

## Реализовано

Endpoint:

`GET /api/v1/runs/{run_id}/events/stream`

Tenant context:

`X-Tenant-ID`

Cursor contract:
1. valid `Last-Event-ID`;
2. иначе `after_seq`;
3. иначе `0`.

Invalid negative/non-numeric cursor → safe typed HTTP `400 INVALID_CURSOR`.

SSE frame:

```text
id: <event.seq>
event: application.event
data: <JSON ApplicationEventView>

```

Гарантии:
- `id == persisted seq`;
- business event type остаётся внутри JSON;
- heartbeat `: keepalive`;
- heartbeat не пишет DB event и не увеличивает seq;
- PostgreSQL `application_events` остаётся source of truth;
- polling использует короткие read UoW;
- long-lived SSE не держит transaction/Run lock;
- disconnect cleanup;
- mid-stream DB/backend failure закрывает stream без raw exception/DSN;
- client затем должен восстановиться из persisted state;
- no Redis/Kafka/NATS.

CORS:
- env `FRONTEND_ORIGINS`;
- exact http(s) origins;
- wildcard запрещён;
- methods GET/POST/OPTIONS;
- headers `X-Tenant-ID`, `Content-Type`, `Accept`, `Last-Event-ID`.

Дополнительно после review:
- non-finite `NaN/Infinity` SSE intervals отвергаются fail-fast;
- wildcard вроде `https://*.vercel.app` отвергается;
- cross-run HTTP streaming isolation усилена тестами.

## 5A evidence

Dedicated real HTTP streaming tests запускают Uvicorn и проверяют:
- unknown run/wrong tenant → 404;
- after_seq ordering;
- Last-Event-ID precedence;
- invalid cursor;
- `id == seq`;
- safe event JSON;
- heartbeat semantics;
- new event after open stream;
- restart + reconnect from persisted cursor;
- writer not blocked;
- cross-run isolation;
- no reasoning/secrets.

DB schema/domain semantics не менялись.

---

# Phase 5B — DONE / PASS

Branch:

`phase-5b-operational-ui`

Final verified HEAD:

`98eae9482456be1fe2cbaf754a2884d682f5d3b5`

Final GitHub Actions:

`37250876126` — **SUCCESS**

## Реализовано

Отдельный package:

`frontend/`

Root historical Node package не превращён в Next.js app.

### Routes

`/`
- product title/context;
- Scenario 1 description;
- backend readiness;
- explicit demo tenant config;
- Start Scenario 1;
- unavailable/error state.

`/runs/[runId]`
- deep-linkable operational console;
- не зависит от предыдущей React navigation history.

### Start flow

1. `POST /api/v1/scenario-1/runs`;
2. configured `NEXT_PUBLIC_DEMO_TENANT_ID` идёт в `X-Tenant-ID`;
3. получает persisted RunStateResponse;
4. navigation `/runs/{run_id}`;
5. bootstrap state + persisted timeline;
6. SSE открывается после bootstrap cursor.

Start не ждёт Gemini.

### Browser/API architecture

Public env:
- `NEXT_PUBLIC_API_BASE_URL`;
- `NEXT_PUBLIC_DEMO_TENANT_ID`.

Tenant env теперь **обязателен**: тихого fallback на `TENANT-8OCT` нет.

Browser идёт напрямую в Product API.
Vercel proxy не добавлен.

SSE client:
- streaming `fetch`;
- header `X-Tenant-ID`;
- `Accept: text/event-stream`;
- собственный incremental SSE parser;
- heartbeat handling;
- parser проверяет `id == persisted seq`.

### Operational console

Top panel:
- Scenario 1;
- Run ID;
- Run status;
- Incident ID;
- connection state;
- last event seq.

Incident:
- incident ID;
- site;
- reported device;
- symptom;
- status;
- `ESCALATED` не трактуется как `RESOLVED`.

Timeline:
- persisted `application_events`;
- seq;
- server timestamp;
- event type;
- safe presentation summary;
- раскрываемый safe persisted payload.

Evidence:
- source type;
- captured timestamp;
- expires_at;
- entity IDs;
- facts;
- explicit label `Typed safe payload`;
- никаких hidden reasoning claims.

Proposal/Approval:
- real persisted proposal only;
- PENDING/REJECTED/STALE/EXECUTED;
- STALE визуально отдельный;
- Approve/Reject используют существующие Phase 4 endpoints;
- обе кнопки disabled во время POST;
- без public «создать proposal» endpoint.

Action/WorkOrder:
- action ID;
- action type;
- action executed timestamp;
- work order ID;
- site/device;
- switch/port;
- work-order creation timestamp;
- UI прямо говорит, что зарегистрированный onsite work order ≠ доказанный repair.

### Review fixes

После повторной проверки 5B исправлено:
- readiness `Phase 55A` → корректный checkpoint label;
- добавлены пропущенные Action ID/executed_at;
- обязательный demo tenant env вместо silent fallback;
- убрана преждевременная homepage-формулировка, обещавшая restart guarantee из 5C;
- evidence payload подписан как safe typed data;
- добавлены API contract tests для tenant header/Approve body/SSE streaming fetch.

## 5B regression evidence

Final run `37250876126`:
- backend full Python: **111 passed**, 1 внешний TestClient warning;
- retained historical Node: green;
- frontend `npm ci`: green;
- TypeScript: green;
- ESLint: green;
- frontend Vitest: **2 files / 8 tests passed**;
- production `next build`: green.

Diff 5A → 5B не меняет:
- `product_backend/`;
- `product_api/`;
- DB schema;
- persistence/domain/approval semantics;
- ADK/Gemini wiring.

---

# Phase 5 — DONE / PASS

Phase 5 полностью закрыта. Ниже — фактический checkpoint/evidence вместо старого
плана `5C → 5D1 → 5D2`.

## 5C — DONE / PASS

Branch: `phase-5c-reconnect-recovery`  
Final verified HEAD: `cd220d8eefaebfe2bebc63a0ab858f1d639859ff`  
Final CI: `37254616583` — **SUCCESS**.

Реализовано и перепроверено:
- authoritative reload bootstrap из Product state + полной persisted timeline pagination;
- per-run cursor = последний принятый persisted `seq`;
- `seq == cursor + 1` accept; `seq <= cursor` dedupe/replay ignore; `seq > cursor + 1` gap recovery;
- persisted backfill с pagination и continuity validation;
- reconnect `0.5 / 1 / 2 / 5 s cap`;
- `Last-Event-ID`/cursor resume;
- bootstrap retry для временных backend/network failures;
- transport state `Live / Reconnecting / Offline/Unavailable`;
- state refresh на `tool.finished`, чтобы persisted Evidence появлялась live;
- fail-closed malformed/non-SSE response handling;
- lost Approve/Reject response recovery по authoritative persisted invariants;
- route remount/isolation при смене run ID;
- WorkOrder/STALE semantics не трактуются как repair/resolved.

Final regression на 5C:
- Python: **111 passed**, 1 внешний TestClient warning;
- historical Node: green;
- frontend: **37/37 tests**;
- typecheck/lint/build: green;
- build больше не переписывает tracked `tsconfig`.

## 5D1 — DONE / PASS / READY FOR MANAGED ACCEPTANCE

Branch: `phase-5d1-isolated-verification`  
Exact release candidate: `47be2321787fa4903702ba38f9c50838e1498033`  
CI: `37255175920` — **SUCCESS**.

D1 не добавляла Playwright dependency. По согласованному решению real browser acceptance
выполняется встроенным браузером Codex/managed agent в D2.

Добавлено/доказано:
- отдельный полный D1 release gate;
- Alembic `upgrade/current/head/check`;
- Phase 3 + 4A/B/C + 5A regression отдельными steps;
- controlled proposal acceptance через существующий `scripts/phase4d_seed_proposal.py`;
- helper создаёт 4 typed persisted Evidence + real `PENDING_APPROVAL` через application service, без public test endpoint и без direct SQL mutation;
- Approve + replay → ровно 1 Approval, 1 ExecutedAction, 1 WorkOrder;
- Reject → `REJECTED`, incident `OPEN`, zero execution/work order;
- exact public env contract:
  - `NEXT_PUBLIC_API_BASE_URL`;
  - `NEXT_PUBLIC_DEMO_TENANT_ID`;
- static runtime-source audit и built `.next/static` audit на server-secret token families;
- `Dockerfile.product` image build green.

D1 final evidence:
- full Python: **115 passed**, 1 внешний TestClient warning;
- frontend: **37/37 tests**;
- historical Node/typecheck/lint/build: green;
- source/bundle security audits: PASS;
- Docker image build: PASS.

D1 артефакты:
- `.github/workflows/phase5d1-isolated-verification.yml`;
- `tests/test_phase5d1_release_candidate.py`;
- `scripts/phase5d1_static_audit.py`;
- `docs/phase5d1-isolated-verification.md`;
- `docs/phase5d2-codex-browser-runbook.md`.

## 5D2 — DONE / PASS — managed acceptance

D2 использовала **тот же exact code commit**
`47be2321787fa4903702ba38f9c50838e1498033`; product code в acceptance не менялся.

Deployment/managed environment:
- Vercel Preview branch: `phase-5d2-managed-acceptance`;
- Vercel Preview: `https://agent-support-l1-git-phase-5d2-managed-acceptance-tonybatony.vercel.app/`;
- Northflank Product API: `https://p01--product-api--yxz5y8myjdln.code.run`;
- existing Northflank project `agent-l1-support`;
- existing PostgreSQL `DB1`, PostgreSQL 16, private networking;
- existing service `product-api`;
- exact Vercel Preview origin добавлен в `FRONTEND_ORIGINS`, localhost сохранён; wildcard CORS не использован;
- backend после env change/restart healthy `1/1`; health endpoint `200`;
- Vercel Preview build/deployment — **Ready**.

### D2 Approve path

Run: `RUN-7396c72a0ea743948da3f8bc7a4af1c5`.

Controlled proposal seed создал ожидающее одобрения предложение с 4 evidence records.
После Approve:
- proposal → `EXECUTED`;
- incident → `ESCALATED`;
- создан ровно один WorkOrder: `WORKORDER-58221abd1c54483a92a0bff33b1d4b5b`;
- repeat same Approve → replay с теми же IDs;
- второй WorkOrder не создан;
- `ESCALATED` не трактуется как repair/resolved.

### D2 Reject path

Run: `RUN-713ff9375d3440d09d50892440b2ba30`.

После Reject:
- proposal → `REJECTED`;
- incident остаётся `OPEN`;
- WorkOrder отсутствует;
- состояние сохраняется после browser reload.

### D2 real Northflank restart / SSE recovery

При открытом accepted run был контролируемо завершён pod Northflank.
Фактически подтверждено:
- UI connection `Offline → Live`;
- timeline/state остались доступны;
- после восстановления сохранился cursor `#9`;
- сохранились 9 timeline events;
- сохранился ровно 1 WorkOrder;
- новый pod отвечал `200` на health, run state, timeline `after_seq=9` и SSE reconnect;
- уже persisted events не потерялись и не задублировались.

Оговорка evidence:
- во время короткого outage **новых событий не возникло**, поэтому D2 не демонстрировала
  непустой catch-up batch после downtime;
- непустой gap/backfill path детерминированно доказан 5C tests;
- managed D2 доказала реальный restart, cursor-preserving reconnect, state preservation
  и отсутствие duplicate/loss уже записанного состояния.

### D2 security acceptance

Проверено:
- static bundle/generated client code на exact SHA;
- application logs;
- filtered HTTP request log lines.

Не обнаружено:
- DB DSN/password;
- Google API key;
- Northflank admin URI;
- raw stack trace;
- hidden reasoning/CoT в public surface.

Northflank aggregate metric показывала **8% 5xx за час**, совпавший с окном
контролируемого restart. В отфильтрованных application HTTP log lines 5xx не найдено,
поэтому **не утверждать**, что глобально за весь час 5xx отсутствовали. Это не блокировало
acceptance, так как restart был намеренной частью теста.

## Phase 5 final decision

Все требуемые checkpoints закрыты:

> **Phase 5 = DONE / PASS.**

Доказаны:
- persisted SSE + `id == seq`;
- reload/reconnect/cursor/dedupe/gap recovery;
- no long-lived DB lock/transaction в SSE path;
- tenant/run isolation;
- real Start → persistent Run/Incident;
- persisted timeline/Evidence/Proposal/Approval/Action/WorkOrder UI;
- real Approve/Reject через существующий Product API;
- decision idempotency / no duplicate WorkOrder;
- WorkOrder ≠ repair/RESOLVED;
- real Vercel ↔ Northflank ↔ DB1 integration;
- real backend restart/reconnect;
- source/bundle/log security checks;
- Phase 3/4/5 regressions green;
- Google ADK/Gemini не протащены в Phase 5 product flow.

Следующая работа — **Phase 6A**.

---

# Phase 6 — Architecture correction + native ADK runtime + live Scenario 1

**Phase 5 PASS выполнен; Phase 6A разрешено начинать.**

Phase 6 больше не означает «надеть ADK поверх всего уже написанного». Она начинается с
обязательной архитектурной коррекции: Product оставляет business/domain responsibilities,
а generic agent-runtime responsibilities возвращаются ADK.

## 6A — mandatory architecture correction / Phase 4B pruning

Это **первое действие Phase 6 до live agent wiring**.

1. Зафиксировать ownership из раздела `ADK owns / Product owns` как implementation rule.
2. Подключить persistent ADK sessions через `DatabaseSessionService` к PostgreSQL. Предпочтительно передать ему уже существующий Product SQLAlchemy `AsyncEngine` через `db_engine=...`, а не создавать без необходимости второй pool/driver; ADK при этом владеет своими session/event/state tables, Product Alembic ими не управляет.
3. Один Product `Run` должен иметь стабильную связь с одной ADK `Session`; допускается хранить только IDs/references, не копируя Product entities в ADK state.
4. Не создавать собственные Session/Event/retry/resume/tracing framework abstractions «для portability».
5. Убрать из tool adapters ручную ответственность за generic runtime lifecycle, **но сохранить** нужный Product boundary: typed request/result mapping, safe error normalization/redaction и domain checks.
6. Перестать считать вручную созданные `tool.started/tool.finished` execution source of truth.
7. Если Phase 5 UI нужны эти event types — строить их как одностороннюю safe projection из ADK events/callbacks в Product `application_events`. Эта projection не является runtime source of truth и её сбой не должен подменять результат tool, повторять уже выполненный side effect или превращать UI-observability failure в business execution semantics.
8. Business events, business state и idempotency оставить Product-owned.
9. Проверить `application_outbox` **в контексте 6C**: нужен ли он как durable `approval committed → ADK resume` delivery/recovery path. Если да — оставить и дать ему конкретного consumer с idempotent delivery semantics. Если нет и другого consumer/use case тоже нет — deprecate и перестать расширять; физическое удаление — только отдельной forward Alembic migration после regression/managed verification. Уже применённые Phase 4 migrations не редактировать.
10. Не удалять полезный Phase 4 domain/persistence код только ради чистоты: cleanup должен уменьшать дальнейший runtime plumbing, а не переписывать Product backend с нуля.

### 6A gate

До перехода к live Scenario 1 должно быть доказано:
- ADK persistent Session survives process restart;
- runtime events/state принадлежат ADK, Product business entities не переехали в ADK state;
- Product approval/idempotency semantics не изменились;
- thin tool boundary вызывает existing application/domain services;
- нет второго самописного agent execution lifecycle рядом с ADK;
- Phase 3/4/5 regression green.

## 6B — native six-tool ADK wiring

Production composition:
- один ADK agent;
- Gemini `gemini-3.5-flash-lite`;
- все 6 Scenario 1 tools registered через штатный ADK tool mechanism;
- tool signatures/model-visible schemas строятся штатным ADK mechanism, без второго custom executor;
- thin wrappers только адаптируют ADK `ToolContext`/arguments к existing Product contracts/services;
- Gemini сам выбирает tool order;
- downstream args реально зависят от предыдущих tool results;
- evidence проходит через existing Product application/domain/persistence path;
- agent-level `retryable` tool failures могут интегрироваться со штатным ADK retry plugin, когда модели нужно повторить/исправить вызов; **Product определяет retryability/error taxonomy**, ADK исполняет generic retry/reflection lifecycle;
- network/provider transport retry остаётся отдельной ответственностью source-system adapter/client и не должен искусственно гоняться через LLM;
- non-retryable domain errors не ретраятся автоматически;
- generic runtime tracing использует ADK/OpenTelemetry, не собственный tracing framework.

## 6C — proposal, human decision и resume

`propose_field_visit` по-прежнему создаёт только Product `PENDING_APPROVAL` proposal.

Human decision остаётся через existing Product Approve/Reject operations.
ADK не становится владельцем approval record или side effects.

Целевой flow:

```text
Gemini / ADK
   ↓
propose_field_visit
   ↓
Product creates PENDING_APPROVAL
   ↓
ADK invocation pauses / waits for external result
   ↓
Human Approve/Reject через Product API/UI
   ↓
Product revalidation + durable business decision + idempotent side effect
   ↓
actual decision/result возвращается в ту же ADK Session/invocation
   ↓
ADK resumes and completes honestly
```

Использовать штатные ADK long-running/HITL/resumability primitives там, где они покрывают
этот flow. Для Scenario 1 preferred baseline — `LongRunningFunctionTool` +
`ResumabilityConfig(is_resumable=True)`/resume по `invocation_id` и исходному function-call id.
Не заменять этот flow простым `require_confirmation=True` на `propose_field_visit`: автоматическая
confirmation gate происходит до выполнения tool, а по Product semantics proposal должен быть
сначала создан и persisted как `PENDING_APPROVAL`, и только потом показан человеку.
Нужна минимальная persisted correlation между Product proposal/run и ADK
`session_id` / `invocation_id` / function-call id: хранить только link/reference, а не строить
собственный execution engine. Отдельно выбрать delivery semantics для уже committed human decision:
- простой post-commit вызов ADK resume допустим только при наличии понятной recovery/reconciliation стратегии на crash между commit и resume;
- если требуется durable eventual resume, существующий Product `application_outbox` может быть оправдан как transactional outbox для idempotent resume-dispatch consumer. Это Product integration reliability, а не дублирование ADK runtime.

## 6D — Scenario 1 E2E / acceptance

Доказать:
- один Run ↔ одна persistent ADK Session;
- все 6 tools реально доступны модели;
- tool order не hard-coded;
- downstream arguments зависят от previous tool outputs;
- restart/resume не создаёт duplicate business side effect;
- approval/reject semantics остаются Phase 4 semantics;
- approved valid proposal создаёт ровно 1 ExecutedAction + 1 WorkOrder;
- reject/stale не создают execution;
- WorkOrder не объявляется repair;
- Product UI продолжает получать safe persisted timeline через Phase 5 SSE;
- runtime tool activity, если отображается, приходит через safe **allowlisted** ADK-event projection; raw prompt/model event/hidden internals не копируются целиком;
- failure этой runtime projection не меняет Product business result и не вызывает повтор side effect;
- hidden reasoning/CoT не сохраняется и не показывается;
- ADK tracing/runtime telemetry не заменяет Product business audit;
- full Phase 3/4/5 regression остаётся green.

## Phase 6 hard FAIL

Считать архитектурной ошибкой, если:
- создаётся новый собственный generic session store при наличии ADK Session service;
- создаётся второй generic **agent-runtime** event/execution engine поверх ADK; Product business/operational `application_events` и UI timeline под этот запрет не подпадают;
- пишется свой generic **agent-level** retry loop вместо ADK plugin без доказанной необходимости; технический transport retry/backoff внутри HTTP/provider adapter допустим и не является agent retry;
- пишется свой generic pause/resume framework вместо ADK resumability без доказанной необходимости;
- runtime tracing заново строится как отдельный Product framework; дополнительные Product/domain spans через стандартный OpenTelemetry допустимы;
- Product business entities переносятся в ADK session state;
- portability к Dify используется как оправдание для дублирования ADK internals;
- Phase 4 business idempotency заменяется framework retry и side effect может выполниться повторно;
- `application_outbox` продолжает расширяться без реального consumer/use case; при этом durable approval→resume dispatch считается валидным consumer/use case и не является дублированием ADK.

Итог Phase 6 = **live six-tool Google ADK integration + полный Scenario 1 E2E на native ADK runtime,
без собственного дубля agent framework**.

---

# Быстрая проверка repository

Backend/local:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
npm test
```

PostgreSQL integration требует `DATABASE_URL`.
Canonical GitHub workflows используют PostgreSQL 16 service container.

Product API:

```bash
python -m product_api
```

Migrations:

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

Frontend:

```bash
cd frontend
npm ci
npm run typecheck
npm run lint
npm test
npm run build
```

---

# Передача следующему исполнителю

Использовать **этот handoff v6.6** как основную точку входа.

Стартовая инструкция:

> Phase 0–5 закрыты. **Phase 5 = DONE / PASS** после 5C recovery, 5D1 isolated
> release verification и 5D2 real Vercel/Northflank/DB1 managed acceptance.
> Managed-accepted Product code commit:
> `47be2321787fa4903702ba38f9c50838e1498033`.
>
> **Начни строго с Phase 6A architecture correction / Phase 4B pruning.**
> Создай новую development branch от exact commit `47be232...`.
> Не подключай live ADK поверх legacy runtime plumbing как ещё один слой.
>
> Ownership boundary из v6.5/v6.6 канонический:
> - ADK owns generic Runner/Session/runtime Events/tool invocation/resume/retry-plugin/tracing mechanics;
> - Product owns business state, six tool implementations/contracts, evidence, proposal/approval/execution, tenant/run isolation, business idempotency, Product API/application_events/SSE/UI и durable integration bridge.
>
> В 6A сначала подключи native persistent ADK Session/Events/state через
> `DatabaseSessionService`, установи stable one Run ↔ one ADK Session correlation,
> убери/перенеси generic agent-runtime responsibilities Phase 4B на ADK primitives
> и не создавай второй custom execution/session/retry/resume framework.
>
> Product PostgreSQL business tables остаются source of truth для business state.
> ADK-owned session/event/state tables остаются source of truth для agent runtime.
> Product Alembic не должен владеть ADK internal tables.
>
> Не ломай Phase 4 approval/idempotency semantics и Phase 5 persisted UI/SSE.
> Любое удаление/перенос legacy runtime plumbing делай только после regression proof.
>
> UI visual debt отдельно зафиксирован: **light/white UI requirement** не терять
> в следующих handoff; текущая dark theme не является поводом перепроектировать
> Phase 6A и должна быть исправлена не позднее Phase 9 polish, если пользователь
> не попросит раньше.

Следующий исполнитель должен вернуть после 6A:
- exact final commit;
- изменённые/удалённые runtime files;
- таблицу `ADK owns / Product owns / retained integration glue` по фактическому code;
- доказательство persistent ADK Session across process restart;
- доказательство stable Run ↔ ADK Session correlation;
- решение по `application_outbox`: concrete durable resume consumer либо deprecation plan;
- Phase 3/4/5 full regression;
- PASS/PARTIAL только для 6A;
- baseline commit для 6B.

---

## Точка проекта на момент выпуска v6.6

**Последнее завершённое действие:** Phase 5D2 managed acceptance.

**Последний managed-accepted code commit:**

`47be2321787fa4903702ba38f9c50838e1498033`

**Последний полный isolated release CI:**

`37255175920` — SUCCESS.

**Phase 5 final status:**

> **DONE / PASS**

**Следующее действие:**

> создать Phase 6A branch от `47be232...` и выполнить mandatory architecture correction / Phase 4B pruning перед live six-tool ADK wiring.

**Каноническое следующее архитектурное изменение:**

> убрать лишнее дублирование generic ADK runtime из Phase 4B/integration layer,
> подключить native persistent ADK Session/Events/resume/retry/tracing, сохранить
> Product domain/business audit/idempotency и только после этого переходить к 6B–6D live Scenario 1.