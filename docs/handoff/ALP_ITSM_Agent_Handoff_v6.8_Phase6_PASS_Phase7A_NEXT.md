# Autonomous L1 Incident Agent

## Canonical cumulative handoff v6.8 — Phase 6 DONE / PASS; Phase 7A NEXT

Дата: 5 октября 2026 года.

Этот файл — **актуальная compact cumulative-точка входа** проекта после полного
**Phase 6 DONE / PASS**. Он создан поверх handoff v6.7 и сохраняет без отката
канонический boundary `ADK owns / Product owns`, Product business semantics
Phase 3/4, persisted UI/SSE Phase 5 и native-ADK решения Phase 6.

Документ намеренно:
- фиксирует фактическое завершение **6A + 6B + 6C + 6D** и managed live evidence;
- заменяет устаревшее состояние «Phase 6A NEXT» на фактический Phase 6 PASS;
- фиксирует final Phase 6 code baseline и тестовый/managed acceptance evidence;
- сохраняет native Google ADK как единственный generic agent runtime: Session/Events/tool lifecycle/resume принадлежат ADK, business truth остаётся Product-owned;
- фиксирует narrow Phase 6D stale-acceptance hook как acceptance-only механизм, выключенный в обычном managed runtime;
- детализирует **Phase 7 / Scenario 2** как `7A → 7B → 7C → 7D → 7E`;
- фиксирует **7A** как automatic operational-event → ADK dispatch плюс согласованные functional UI changes (Incidents/Observations list→detail и scrollable info panels);
- сохраняет известный light/white UI visual debt отдельно от этих functional UI changes: theme/polish по-прежнему не является gate 7A.

Текущая точка остановки:

> **Phase 6 = DONE / PASS. Phase 7A = NEXT.**

Канонический baseline для следующей работы:

- repository: `hotsbelima/Agent-Supportl1`;
- branch: `phase-6c-human-decision-resume`;
- final Phase 6 code commit: `919f7a61c9b7d390890de65cd94cd15452ef5aff`;
- Northflank `product-api` managed acceptance выполнен на exact commit `919f7a...`;
- stale-acceptance temporary env/token после live-проверки удалены;
- Phase 7 development branch создавать **от exact commit `919f7a...`**.

---

## Как пользоваться этим handoff

При конфликте информации приоритет:

1. этот cumulative handoff v6.8;
2. repository code на final Phase 6 commit `919f7a61c9b7d390890de65cd94cd15452ef5aff`;
3. Phase 6 verification docs/tests и managed acceptance evidence;
4. handoff v6.6/v6.5 для history Phase 6 ownership/boundary rationale;
5. Phase 5 managed UI/SSE acceptance evidence;
6. Phase 4 verified Product persistence/application evidence;
7. Phase 3 contracts;
8. исторические Phase 1/2 spike docs.

Следующий исполнитель **не должен заново проектировать Phase 0–6**.
Если текущий code contradicts этому handoff, сначала воспроизвести проблему test'ом.

После major checkpoint по-прежнему:
- фиксировать exact final commit;
- фиксировать CI/evidence;
- не объявлять PASS без выполнения checkpoint criteria;
- ownership boundary `ADK owns / Product owns` не пересматривать без конкретного воспроизводимого дефекта или проверенного ограничения ADK;
- Scenario 1 regression считать обязательным safety net при изменениях Phase 7.

## Краткий статус

| Фаза | Статус | Результат |
| --- | --- | --- |
| 0 | **DONE** | Architecture, Scenario 1, fixture/world truth, evidence/approval semantics. |
| 1 | **DONE** | Local Google ADK/Gemini dependent two-tool runtime 3/3. |
| 2 | **DONE** | Тот же runtime на Northflank 3/3. |
| 3 | **DONE / PASS** | Domain/contracts, validators, evidence, approval/execution boundary, six-tool adapter layer. |
| 4 | **DONE / PASS** | PostgreSQL persistence + persisted lifecycle/events + Product API + managed Northflank acceptance. |
| 5 | **DONE / PASS** | Persisted SSE + operational UI + reload/reconnect/recovery + Vercel/Northflank/DB1 managed acceptance. |
| 6A | **DONE / PASS** | Native persistent ADK Session/Events/state; one Run ↔ one ADK Session; legacy generic runtime ownership pruned. |
| 6B | **DONE / PASS** | One native ADK/Gemini agent with six Product tools; live model-driven dependent tool calling verified. |
| 6C | **DONE / PASS** | Product proposal first → native ADK long-running pause → Product human decision → same-invocation resume/recovery. |
| 6D | **DONE / PASS** | Managed Scenario 1 E2E: Approve/Reject/stale/restart/replay/UI/SSE + full regression on exact final SHA. |
| 6 | **DONE / PASS** | Native Google ADK runtime + complete Scenario 1 live vertical slice, without duplicate custom agent framework. |
| 7 | **NEXT — 7A** | 7A automatic event→agent dispatch + UI restructuring, затем Scenario 2 multi-event correlation → Major Incident flow. |
| 8 | **PLANNED** | Scenario 3: disconfirmed hypothesis → replanning → new tool sequence. |
| 9 | **PLANNED** | Polish/hardening/public deploy; light/white UI debt must be closed no later than here. |

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

После Phase 6:

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

Phase 6 закрепила ADK как **agent runtime**, а не как второй product backend и не как слой,
который надо заново реализовывать внутри проекта:

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

### Ownership boundary Phase 6+ — сохраняется в Phase 7

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

- текущие Scenario 1 business entities (`Run`, `Incident`, `Evidence`, `ActionProposal`, `Approval`, `ExecutedAction`, `FieldServiceWorkOrder`) и будущие typed scenario-specific business entities;
- source-system adapters и реальные implementation bodies Product tools: шести Scenario 1 tools и добавляемых scenario-specific tools следующих фаз;
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
- один Product Run ↔ одна persistent ADK Session в Phase 6+; Phase 7 сохраняет ту же correlation rule;
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
- Google ADK `2.10.0` — **live Product runtime**, persistent Session/Events/resumability verified;
- Gemini `gemini-3.5-flash-lite` — **live managed Product agent model**;
- FastAPI `0.141.1`;
- Uvicorn `0.54.0`;
- pytest `8.4.2`;
- SQLAlchemy `2.0.54`;
- Alembic `1.20.0`;
- psycopg `3.3.6`;
- PostgreSQL `16`.

### ADK 2.10.0 capability baseline for Phase 6+

Ownership выше и реализованный Phase 6 runtime сверялись с pinned Python `google-adk==2.10.0`, а не только с более новой документацией. В этой версии уже присутствуют нужные framework primitives: `Runner`, persistent `DatabaseSessionService` с SQLAlchemy `AsyncEngine`, `Session.state`/persisted Events, `FunctionTool`/`ToolContext`, `LongRunningFunctionTool`, `ResumabilityConfig`, `ReflectAndRetryToolPlugin`, callback/plugin lifecycle и OpenTelemetry tracing support. Поэтому для этих generic runtime responsibilities свой framework не нужен. При этом ADK не знает Product semantics: Incident/Evidence/Proposal/Approval, business idempotency, authorization policy, safe Product error contract и durable delivery business decision → resume остаются application/integration responsibilities.

Frontend baseline after Phase 6:
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

### Шесть Scenario 1 product tools — verified Phase 6 baseline

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

### Phase 4B architectural note — resolved by Phase 6

Phase 4 остаётся **PASS для своего checkpoint**. Review после 5B обнаружил в 4B лишний
generic agent-runtime plumbing; Phase 6 его не переписала с нуля, а вернула generic runtime
responsibilities штатному Google ADK, сохранив Product business audit/idempotency.

**Осталось Product-owned:**
- `proposal.created`;
- `approval.decided`;
- `action.executed`;
- `run.status_changed`;
- `finding.recorded` и другие safe business/operational facts;
- per-run business timeline, seq, tenant isolation;
- DB constraints/idempotency/business audit.

**Фактический результат Phase 6 correction:**
- ручные `tool.started` / `tool.finished` больше не используются как собственный execution lifecycle;
- `DefaultScenario1ToolAdapter` не владеет generic runtime start/finish bookkeeping;
- agent runtime state хранится в native ADK Session/Events, а не во втором Product runtime store;
- generic retry/pause/resume lifecycle реализован ADK primitives/plugins, а не самописным framework;
- legacy `application_outbox` table из применённой Phase 4 migration физически сохранена, но generic producer/consumer в Phase 6 отсутствует; новые обычные `application_events` outbox rows не создают;
- для committed human decision → ADK resume в 6C выбран post-commit resume + persisted ADK Event reconciliation/replay path, поэтому отдельный outbox consumer не понадобился.

Если в будущей фазе UI понадобится runtime tool activity, её можно добавить только как
**safe allowlisted projection из ADK runtime events в Product `application_events`**. ADK остаётся
runtime source of truth; Product timeline — presentation/business-audit surface, не второй execution engine.
Legacy outbox не расширять без нового concrete durable consumer/use case; физическое удаление —
только отдельной forward Alembic migration после regression/managed verification.

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

Исторически после Phase 5 следующей работой была **Phase 6A**; в текущем handoff 6A–6D уже закрыты.

---

# Phase 6 — DONE / PASS — native ADK runtime + live Scenario 1

Phase 6 полностью закрыта. Целевой результат достигнут: generic agent-runtime responsibility
возвращена Google ADK, Product сохранил business truth/guardrails/idempotency, а полный
Scenario 1 прошёл deterministic/integration и managed live acceptance.

## 6A — DONE / PASS — native ADK persistence / runtime ownership correction

Final checkpoint commit:

`f0c2f9c8f3c37656146155ecbcf7f90fbae872a9`

Выполнено:
- native `DatabaseSessionService(db_engine=existing Product AsyncEngine)`; второй DB pool не создавался;
- stable correlation: `app_name=autonomous-l1-incident-agent`, `user_id=tenant_id`, `session_id=run_id`;
- race-safe ensure использует native ADK `AlreadyExistsError` + reread;
- ADK-owned Session/Events/state переживают process restart;
- Product entities не перенесены в ADK state;
- generic `application_events` больше не порождают новый outbox/runtime lifecycle;
- manual `tool.started/tool.finished` не являются runtime source of truth;
- custom generic session/execution framework рядом с ADK не создан.

Verification:
- focused 6A tests: 4 PASS;
- full regression на checkpoint: 119 Python + 37 frontend PASS;
- Product Alembic не владеет ADK internal tables.

## 6B — DONE / PASS — native six-tool Gemini/ADK wiring

Final accepted baseline:

`cc7e6be3cb5ffa967839520451fefd5d65cc5ee5`

Выполнено:
- один native ADK `LlmAgent` + `Runner`;
- model `gemini-3.5-flash-lite`;
- все шесть Scenario 1 Product tools зарегистрированы через native ADK tool mechanism;
- `ToolContext` инжектит trusted tenant/run; модель не выбирает tenant/run;
- model-facing schemas явно требуют affected `reported_device_id`, diagnostic `attachment_id` из предыдущего CMDB result и реальные prior evidence IDs;
- Product retryability/error taxonomy сохранена; generic model retry/reflection использует ADK plugin, non-retryable domain errors не гоняются повторно;
- `propose_field_visit` остаётся обычным Product tool и создаёт только `PENDING_APPROVAL`.

Live evidence:
- три независимых успешных Gemini runs на одном exact code baseline;
- типичный path: `get_device → get_site_health → run_diagnostic → search_kb → propose_field_visit`;
- `search_incidents` был зарегистрирован и доступен модели уже в 6B; acceptance 6B не принуждал его искусственно ради coverage, а фактический live-вызов этого tool позже подтверждён в 6D trace;
- каждый accepted run: Run `WAITING_APPROVAL`, proposal `PENDING_APPROVAL`, 4 required Evidence, `Approval=0`, `ExecutedAction=0`, `WorkOrder=0`;
- Google 429 free-tier quota отдельно классифицирован как provider limitation, а не Product/agent defect.

## 6C — DONE / PASS — Product decision + native ADK pause/resume

Verified checkpoint before 6D hook:

`9c24abb35a4f4e5a53f4c68661b2e10e10ec40a9`

Ключевое архитектурное решение:
- **не** превращать `propose_field_visit` в `LongRunningFunctionTool`, потому что ADK 2.10 resumability останавливает invocation на long-running function-call event до выполнения callable;
- сначала обычный Product `propose_field_visit` реально persists `PENDING_APPROVAL`;
- затем агент вызывает отдельный native `LongRunningFunctionTool` `await_human_decision(proposal_id)`;
- `App` использует `ResumabilityConfig(is_resumable=True)`;
- correlation не дублируется в собственной runtime-таблице: persistent ADK Events уже содержат `proposal_id` argument + `invocation_id` + original function-call id, а `session_id=run_id` установлен в 6A;
- Approve/Reject сначала выполняют и commit'ят Product business decision; только после commit API пытается resume ADK;
- committed Product decision не объявляется откатанным из-за provider/runtime failure после commit;
- recovery различает: response ещё не доставлен / FunctionResponse уже persisted, но continuation не завершён / invocation уже completed;
- identical replay не инжектит второй FunctionResponse и не создаёт второй business side effect;
- WorkOrder в resume payload всегда сопровождается `repair_confirmed=false`.

Deterministic/integration verification:
- native in-memory pause → same-invocation resume;
- persisted pause → new engine/runtime → resume;
- crash after FunctionResponse persistence → continuation without duplicate delivery;
- valid Approve, Reject, stale Approve, retryable revalidation failure;
- Product-first commit / deferred resume / replay reconciliation;
- full Python regression: 136 PASS;
- frontend: 37 PASS;
- Alembic clean, frontend typecheck/lint/build/static audit PASS, Docker build PASS.

## 6D — DONE / PASS — managed Scenario 1 E2E

Final Phase 6 code commit:

`919f7a61c9b7d390890de65cd94cd15452ef5aff`

Managed environment:
- Northflank project/service: `agent-l1-support` / `product-api`;
- PostgreSQL 16 managed DB1;
- Vercel operational UI from Phase 5 remains connected to Product API/SSE;
- final code deployed and health/readiness verified on exact SHA.

### Managed live evidence

Подтверждено на реальном Gemini/ADK/Product flow:
- один Product Run ↔ одна persistent ADK Session;
- все шесть Scenario 1 Product tools доступны модели и все встретились в live traces;
- tool order не hard-coded: live runs отличались, включая run с `search_incidents`;
- `run_diagnostic.target_id` происходил из предыдущего CMDB/topology `attachment_id`;
- proposal evidence IDs происходили из реально созданных prior Evidence;
- proposal → `PENDING_APPROVAL` → native `await_human_decision` pause;
- restart pod между pause и human decision не ломает resume того же invocation;
- valid Approve создаёт ровно 1 Approval + 1 ExecutedAction + 1 WorkOrder;
- replay того же решения не создаёт duplicate side effect;
- Reject создаёт Approval(REJECTED), но 0 ExecutedAction / 0 WorkOrder, incident остаётся OPEN;
- финальные ответы модели не выдают WorkOrder за завершённый repair;
- Product UI/SSE показывает persisted business timeline, а не raw ADK/model internals.

### Known UI/start behavior after Phase 6 — explicitly assigned to 7A

Phase 6D browser verification выявила важное текущее поведение, которое **не блокировало Phase 6**,
но теперь является обязательным integration debt Phase 7A:
- UI-кнопка **Start Scenario 1** сейчас создаёт persistent Product Run/Incident, но сама не вызывает Gemini/ADK;
- live agent сейчас запускается отдельным `POST /api/v1/runs/{run_id}/agent/invoke`;
- Phase 6D UI/SSE proof выполнялся после такого отдельного invoke и подтвердил persisted Evidence/proposal/timeline;
- часть стартового UI-текста всё ещё отражает Phase 5/product-run semantics.

Целевой UX/architecture после 7A:
- **не добавлять** пользовательскую кнопку «Запустить агента» / «Начать расследование»;
- пользовательская кнопка **Start simulation** означает только запуск симуляции / инъекцию первого simulated operational event;
- incoming operational event сначала становится Product-owned persisted fact/event;
- backend после persist автоматически dispatch'ит/продолжает соответствующую ADK Session;
- frontend не является orchestrator'ом agent runtime и не должен вручную дергать `/agent/invoke` как часть demo UX;
- существующий `/agent/invoke` можно временно оставить как internal/debug/compatibility endpoint, но не как пользовательский шаг;
- агент **не держит Gemini постоянно работающим и не poll'ит Monitoring через LLM 24/7**: источники/симулятор доставляют события, а backend event-driven будит/продолжает агента только когда есть новый operational signal.

### Stale Approve managed acceptance

Чтобы физически воспроизвести изменение authoritative monitoring state **того же Run**
между pause и Approve, в final Phase 6 commit добавлен narrow acceptance-only hook:

`POST /__acceptance/phase6d/runs/{run_id}/access-link-state`

Safety boundary:
- hidden from OpenAPI;
- disabled by default;
- требует `PHASE6D_ACCEPTANCE_HOOKS=1` и отдельный `PHASE6D_ACCEPTANCE_TOKEN`;
- wrong/disabled access выглядит как 404;
- разрешён только для `WAITING_APPROVAL` Run с `PENDING_APPROVAL`;
- state override scoped по `(tenant_id, run_id)`;
- process-local; не является Product business state, ADK state или timeline event;
- после managed stale acceptance temporary env/token **удалены**.

Live stale result:
- authoritative access-link state того же paused Run переключён на `UP`;
- обычный Approve выполнил Product revalidation;
- Approval = `APPROVED`;
- proposal = `STALE`;
- Run = `ACTIVE`;
- incident = `OPEN`;
- same ADK invocation resumed;
- `ExecutedAction = 0`;
- `WorkOrder = 0`;
- final model response не заявлял execution/repair.

### Final regression / Phase 6 decision

На exact final SHA `919f7a...` до live stale-run уже полностью прошёл immutable-code regression:
- Python: **140 passed**, 3 warnings;
- retained Node: **5/5**;
- frontend Vitest: **37 passed**;
- dependency consistency / Python compile: PASS;
- Alembic upgrade/current/check: PASS, no new operations;
- frontend typecheck/lint/production build/static audit: PASS;
- Product Docker image build: PASS;
- Phase 6A workflow: SUCCESS;
- Phase 6B workflow deterministic/build gates: PASS; его historical GitHub live Gemini step не выполняется без `GOOGLE_API_KEY`, что не является кодовым regression.

После stale live-run код не менялся, поэтому дополнительный rerun того же immutable SHA не является отдельным Phase 6 blocker.

> **Phase 6 = DONE / PASS.**

---

# Phase 7 — NEXT — Scenario 2: multi-event correlation → Major Incident

Phase 7 не должна переписывать Phase 6 runtime. Она добавляет второй бизнес-сценарий поверх уже
проверенной связки Product + persistent ADK Session/Events + native tools + human pause/resume.

Исторические handoff фиксировали для Phase 7 только high-level business scope. Разбиение
`7A → 7B → 7C → 7D → 7E`, typed contracts и acceptance criteria ниже — **новый детализированный
implementation contract v6.8**, который ещё не реализован и должен быть зафиксирован тестами
по мере выполнения.

Исходный продуктовый смысл Scenario 2 сохраняется из раннего project scope:
- сначала приходит monitoring alert в одном магазине;
- затем user/ITSM ticket;
- затем похожие сигналы из других **географически независимых** магазинов;
- агент должен перестать трактовать их как отдельные локальные проблемы;
- проверить общий внешний dependency;
- при достаточном evidence предложить Major Incident;
- критическое действие выполняется только после human approval.

Carried-forward world constraints для Phase 7 (exact IDs/event sequence ещё фиксируются в 7B):
- сеть **«8 Щупалец»**;
- минимум `SITE-KZN-017` и отдельный Samara site; третий site допустим как дополнительный correlation signal;
- локальные site/network checks — healthy, то есть нет evidence общей локальной network failure;
- symptom/correlation key: `payment_gateway_timeout`;
- общий внешний provider/dependency: `AcmePay`;
- `AcmePay = DEGRADED` в happy-path correlation state;
- существующего Major Incident для этого outage initially нет;
- exact hidden world state должен быть deterministic fixture truth, но агенту нельзя отдавать финальный вывод напрямую в initial event.

## Phase 7 architecture rules

Сохраняются без пересмотра:
- сохраняется **single-agent architecture**: не строить cooperating multi-agent orchestrator; scenario-specific tool surface можно компоновать вокруг того же native ADK runtime;
- один Product Run ↔ одна persistent ADK Session;
- ADK owns generic Session/Events/invocation/tool lifecycle/resume;
- Product owns operational signals, incidents, evidence, proposal/approval/execution, tenant/run isolation, business idempotency, Product audit/SSE/UI;
- incoming events сначала становятся Product-owned persisted facts, и только затем передаются агенту;
- hidden CoT/raw model events не копируются в Product timeline;
- human Approve/Reject остаются Product application operations, не model tools;
- Scenario 1 contracts/tests нельзя ломать ради Scenario 2.

### Important domain rule

Текущий Scenario 1 `ActionProposal`/execution model содержит field-visit-specific fields
(`device_id`, `DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE`, `ONSITE_FIELD_VISIT`).
**Запрещено** проталкивать Scenario 2 через fake/dummy `device_id`, diagnosis или WorkOrder.

В 7B нужно ввести typed Scenario 2 proposal/action contract либо безопасно выделить
общую proposal/approval основу с discriminated scenario-specific payloads. Любая generalization
должна сохранить строгую типизацию и доказать Scenario 1 regression. Не делать набор nullable
полей «на все случаи» только ради быстрого переиспользования таблицы.

## 7A — automatic event → agent dispatch + operational UI restructuring

7A закрывает integration/UX debt Phase 6 **до** построения Scenario 2 contracts. Это не новая
agent architecture: native ADK runtime Phase 6 сохраняется. Меняется способ входа события в runtime
и presentation operational state в UI.

### 7A.1 — event-driven automatic dispatch

Целевой demo flow:

```text
User clicks Start simulation
        ↓
simulator emits first operational event
        ↓
Product backend persists event / creates or resolves Run
        ↓
backend automatically invokes or continues the Run's persistent ADK Session
        ↓
Gemini investigates using native ADK tools
        ↓
Product Evidence / Proposal / status changes
        ↓
persisted SSE updates operational UI
```

Правила:
- **никакой отдельной user-facing кнопки «Запустить агента»**;
- `Start simulation` запускает simulated environment/event source, а не напрямую Gemini;
- browser/front-end не должен быть agent orchestrator'ом;
- operational event сначала persist Product-side, затем инициирует agent dispatch;
- dispatch должен использовать существующую stable `Run ↔ ADK Session` correlation;
- повтор/duplicate delivery одного и того же simulated event не должен создавать duplicate business side effect или второй независимый agent runtime;
- если после persist event agent dispatch временно не удался, persisted Product fact не теряется; recovery/retry должен быть явным и idempotent, без самописного второго generic agent loop;
- LLM не работает «в фоне постоянно»: event source/Monitoring/ITSM/simulator доставляет событие, после чего backend event-driven запускает/продолжает invocation.

Для Scenario 1 после 7A ожидаемый пользовательский путь: `Start simulation` → без ручного internal API call
агент сам доходит до расследования/evidence/proposal и при необходимости `WAITING_APPROVAL`; human
Approve/Reject остаются отдельным Product-owned действием.

### 7A.2 — Incidents UI: list → realtime detail

Текущая карточка одного incident заменяется на список incidents текущего Run/case.

List row показывает минимум:
- короткое название/summary тикета (для текущего Scenario 1 допустимо безопасно использовать существующий `symptom` как display summary, не добавляя фиктивное domain field только ради UI);
- site;
- status;
- кнопку **Подробнее**.

`Подробнее` **не открывает modal и не ведёт на новую страницу**. В той же панели список заменяется
на текущий detail-view выбранного incident. В detail есть `← Назад к списку`.

Realtime semantics:
- list и открытый detail bootstrap'ятся из persisted Product state;
- SSE updates должны обновлять соответствующую строку и открытый detail без reload;
- если выбранный incident изменил status/данные, detail обновляется на месте;
- navigation list↔detail не должна терять realtime subscription/cursor.

### 7A.3 — Observations UI: list → realtime detail

`Observations` переводится на тот же interaction pattern. Под observation здесь понимается safe
Product observation/evidence representation, а не raw ADK/model event или hidden reasoning.

List row показывает минимум:
- type/short observation name;
- source и/или site/entity context;
- timestamp и status/state, если он применим к типу observation;
- кнопку **Подробнее**.

`Подробнее` заменяет список внутри той же панели на safe typed detail; `← Назад к списку` возвращает
к списку. List/detail продолжают realtime обновляться через persisted Product state/SSE. Raw prompt,
CoT и provider internals в observation detail не добавлять.

### 7A.4 — scrollable information panels / desktop + mobile

Центральные information panels/cards, содержимое которых может превышать доступную высоту, должны
иметь внутренний vertical scroll вместо расширения страницы/обрезания content:
- фиксировать/ограничивать usable panel height согласно текущему responsive layout;
- `overflow-y` включается только при реальном overflow;
- scrollbar/thumb видим только когда content уже не помещается;
- desktop: когда pointer находится внутри scrollable panel, mouse wheel/trackpad scroll прокручивает её содержимое естественно;
- не перехватывать wheel глобально custom-JS'ом без необходимости — предпочесть native scrolling;
- mobile/tablet: touch swipe внутри панели прокручивает её content; scrollbar не должен быть единственным способом навигации;
- nested scrolling не должно ломать общий page scroll: при достижении верхней/нижней границы пользователь должен оставаться способен продолжить навигацию страницы;
- никаких horizontal overflow/сломанной ширины карточек на узком viewport.

### 7A gate

До 7B должно быть доказано:
1. `Start simulation` создаёт/инъектит первый persisted operational event и **без отдельного ручного `/agent/invoke`** приводит к automatic ADK investigation того же Run.
2. В demo UI отсутствует user-facing «Запустить агента»; frontend не orchestrates ADK lifecycle.
3. Scenario 1 из UI автоматически доходит до Evidence/proposal/`WAITING_APPROVAL` там, где это требуется fixture'ом.
4. Existing Phase 6 native pause/resume, Approve/Reject/replay semantics не сломаны.
5. Incidents: список `summary | site | status | Подробнее`, same-panel detail + `← Назад к списку`, realtime updates.
6. Observations: список `type/name | source/site/entity | timestamp/status | Подробнее`, same-panel safe detail + realtime updates.
7. Overflow panels корректно scrollятся wheel/trackpad на desktop и touch/swipe на mobile; scrollbar появляется только при overflow.
8. Reload/reconnect/SSE cursor semantics Phase 5 остаются green.
9. Full Scenario 1 backend/frontend regression, typecheck/lint/build/Alembic/Docker остаются green на exact 7A SHA.

## 7B — exact Scenario 2 spec + Product/domain contracts

Сначала зафиксировать canonical fixture и contracts до live Gemini:

1. Определить точную последовательность входящих events/signals и canonical IDs.
2. Добавить Product-owned persisted representation входящего operational signal/event с `tenant_id`, `run_id`, source, site, symptom/correlation key, server UTC timestamp и safe payload.
3. Один Scenario 2 Run должен уметь накопить несколько persisted operational signals/events из разных sites. Нужно отдельно решить в 7B, какие из них становятся Product `Incident`, а какие остаются typed signal/event facts; не создавать лишние Incident entities только ради корреляции.
4. Добавить typed Evidence для:
   - incoming/correlated operational signals;
   - local site/network health checks;
   - service/dependency mapping;
   - external dependency status;
   - existing Major Incident search.
5. Добавить typed proposal/action semantics для `CREATE_MAJOR_INCIDENT` без dummy Scenario 1 fields.
6. Определить Product revalidation rules на Approve:
   - correlated multi-site evidence всё ещё актуально;
   - common external dependency всё ещё DEGRADED;
   - existing Major Incident всё ещё отсутствует;
   - duplicate/replay не создаёт второй Major Incident.
7. Reject должен создать human audit decision и 0 Major Incident execution.
8. Stale Approve: provider recovered **или** подходящий Major Incident уже появился → proposal `STALE`, 0 execution.
9. Ранний scope упоминал `create Major Incident / массовое уведомление` как критическое действие после approval. Для Phase 7 обязательным execution считать typed Major Incident creation; массовое уведомление не отправлять во внешнюю систему, а при необходимости показать как Product-owned deterministic simulated notification record **после** успешного approval/execution.

### 7B gate

До event-driven Scenario 2 ingestion должны быть unit/domain tests на:
- cross-tenant/cross-run isolation;
- evidence provenance/currentness;
- insufficient single-site evidence → Major Incident proposal rejected;
- fabricated/cross-run evidence rejected;
- duplicate Major Incident prevention;
- Approve/Reject/stale/replay semantics;
- Scenario 1 full regression remains green.

## 7C — event-driven ingestion + state between events

Цель 7C — доказать **event-driven state**, а не запустить весь сценарий одним огромным prompt.

Нужен Product-owned typed event ingestion/simulator для Scenario 2:
- event 1 persist → agent invocation 1 in same ADK Session;
- event 2 persist → agent invocation 2 in same ADK Session;
- event 3+ persist → subsequent invocation in same ADK Session;
- Product event/signal state сохраняется независимо от ADK history;
- ADK persistent Session даёт runtime conversational continuity между invocations;
- process restart между events не теряет ни Product facts, ни ADK session continuity.

Canonical behavior:
- после первого single-site alert агент **не должен** создавать Major Incident только по одному сигналу;
- user ticket/second same-site signal усиливает факт проблемы, но не доказывает cross-site outage;
- сигнал из географически независимого site должен заставить агента рассмотреть common dependency;
- final correlation conclusion должен опираться на persisted events + tool evidence, а не на зашитую sequence condition в backend.

Implementation boundary:
- simulator/ingestion генерирует/принимает facts; он **не** решает за модель, что это Major Incident;
- backend не должен иметь hard-coded `if event_count >= N: propose_major_incident`;
- timestamp source остаётся server UTC, как в текущем Product audit.
- для stale acceptance предусмотреть controlled Scenario 2 fixture/simulator transition (`AcmePay DEGRADED → HEALTHY` или появление matching Major Incident); не переиспользовать Phase 6D access-link hook и не мутировать Product DB вручную.

## 7D — Scenario 2 native ADK tools + Major Incident HITL

Необязательно показывать Scenario 2 модели все шесть field-visit tools. Использовать минимальный,
семантически правильный scenario-specific tool surface поверх того же native ADK runtime.

Минимально нужны read/action capabilities:
- local site/service health check для исключения локального outage;
- service/dependency mapping, чтобы common provider не был просто зашит в prompt;
- external dependency/provider status check;
- search existing Major Incidents для duplicate prevention;
- `propose_major_incident(...)` с реальными prior Evidence IDs.

Названия конкретных функций можно уточнить в 7B, но model-visible schema должен быть typed,
а trusted tenant/run context снова инжектируется вне model arguments.

Happy path:

```text
multiple persisted signals across sites
        ↓
same persistent ADK Session, multiple invocations
        ↓
local sites healthy / common symptom observed
        ↓
service dependency mapping → AcmePay
        ↓
external dependency status → DEGRADED
        ↓
search existing major incidents → none
        ↓
propose_major_incident(real evidence ids)
        ↓
Product PENDING_APPROVAL
        ↓
native await_human_decision pause
        ↓
Product Approve/Reject + revalidation
        ↓
same ADK invocation resume
```

Re-use Phase 6C native wait/resume mechanism. Не писать второй pause/resume framework и не делать
Approve/Reject model tools.

## 7E — Scenario 2 managed E2E / acceptance

Phase 7 = PASS только после live managed доказательства на Northflank/Gemini.

Обязательные сценарии:

1. **No premature escalation**
   - first single-site event(s) не создают Major Incident proposal;
   - Run остаётся активным и ждёт следующих events.
2. **Cross-site correlation / happy path**
   - events из независимых sites приходят последовательно;
   - один Run ↔ одна persistent ADK Session across all events;
   - Gemini использует prior session context + Product/tool evidence;
   - dependency определяется через tool evidence;
   - AcmePay status `DEGRADED` подтверждён tool result;
   - existing Major Incident search возвращает none;
   - создаётся ровно один `PENDING_APPROVAL` Major Incident proposal.
3. **Approve**
   - Product revalidation проходит;
   - создаётся ровно один Major Incident execution/record;
   - same ADK invocation resumes;
   - final answer не заявляет recovery внешнего provider без evidence.
4. **Replay**
   - identical Approve/retry не создаёт второй Major Incident/notification side effect.
5. **Reject**
   - Approval(REJECTED), proposal REJECTED, 0 Major Incident execution.
6. **Stale**
   - AcmePay recovered или matching Major Incident появился до Approve;
   - Approval(APPROVED), proposal STALE, 0 execution;
   - same invocation resumes с честным result.
7. **Restart/state**
   - restart между входящими events не теряет accumulated Product facts/ADK session;
   - restart между proposal pause и human decision не ломает resume.
8. **UI/SSE**
   - persisted operational timeline показывает incoming signals, safe evidence, proposal/approval/execution;
   - raw prompt/CoT/provider internals не показываются.
9. **Regression**
   - полный Scenario 1 Phase 6 regression остаётся green;
   - Phase 7 tests + frontend/build/Alembic/Docker green на exact final SHA.

## Phase 7 hard FAIL

Не объявлять Phase 7 PASS, если:
- correlation фактически hard-coded по номеру event, а не получается через model + evidence;
- Product incoming events существуют только в ADK chat history и не persisted Product-side;
- common dependency `AcmePay` просто сообщается модели как готовый вывод вместо tool-backed discovery/check;
- Major Incident создаётся до human approval;
- dummy Scenario 1 device/diagnosis/work-order fields используются для Major Incident action;
- replay/concurrent decision может создать duplicate Major Incident;
- cross-tenant/cross-run event/evidence смешивается;
- restart теряет multi-event state;
- ради Scenario 2 создаётся второй generic agent runtime/session/resume framework;
- Scenario 1 regressions ломаются и это списывается на «новый сценарий».

## Phase 7 expected physical result

После PASS Phase 7 в repository/managed demo должны существовать:
- automatic persisted operational-event → ADK dispatch без user-facing «Запустить агента»;
- operational UI с realtime Incidents/Observations list→detail и responsive internal scrolling;
- Scenario 2 deterministic world/fixtures;
- typed multi-event Product ingestion/state;
- Product/domain Evidence + Major Incident proposal/approval/execution contracts;
- scenario-specific native ADK tool surface;
- same-session multi-invocation correlation behavior;
- reused native human pause/resume;
- persisted UI/SSE timeline для Scenario 2;
- deterministic + managed live acceptance evidence.

Phase 8 после этого остаётся **Scenario 3: disconfirmed hypothesis / replanning**.

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

Использовать **этот handoff v6.8** как основную точку входа.

Стартовая инструкция:

> Phase 0–6 закрыты. **Phase 6 = DONE / PASS** на final code commit
> `919f7a61c9b7d390890de65cd94cd15452ef5aff`.
>
> Создай Phase 7 development branch **от exact `919f7a...`**.
> Не перепроектируй native ADK runtime и не создавай multi-agent framework.
>
> Phase 7 = Scenario 2: sequential operational events from different stores,
> persistent state across events, correlation, common external dependency check,
> Major Incident proposal, Product human approval/reject/stale/replay and managed E2E.
>
> Сначала сделай **7A automatic event→agent dispatch + operational UI restructuring**.
> `Start simulation` должен только породить первый simulated operational event; после Product persist
> backend сам запускает/продолжает persistent ADK Session. Не добавляй кнопку «Запустить агента» и
> не оставляй browser orchestration через ручной `/agent/invoke` как demo UX. Одновременно переделай
> Incidents и Observations в realtime list→same-panel detail с `← Назад к списку`, и добавь native
> overflow scrolling для information panels на desktop/mobile.
>
> Затем **7B exact Scenario 2 spec/domain contracts**. Текущий Scenario 1 proposal/action
> field-visit-specific; запрещено использовать fake `device_id`, fake diagnosis или WorkOrder
> для Major Incident. Введи typed Scenario 2 semantics и сохрани Scenario 1 regression.
>
> Затем **7C event ingestion/state**: каждый incoming Scenario 2 event сначала persist Product-side,
> потом вызывает новый invocation в **той же ADK Session**. Backend не должен коррелировать
> outage через `if event_count >= N`; correlation остаётся model/evidence behavior.
>
> Затем **7D native Scenario 2 tools + HITL**: dependency mapping/status,
> existing Major Incident check и `propose_major_incident(...)`; human decision использует
> уже проверенный Phase 6C native `await_human_decision`/resume mechanism.
>
> Заверши **7E managed E2E**: no-premature-escalation, happy-path Approve, replay,
> Reject, stale, restart between events, restart around approval, safe UI/SSE, full Scenario 1 regression.
>
> Product PostgreSQL остаётся source of truth для business state/events/evidence.
> ADK Session/Events остаются source of truth для generic agent runtime state.
> Hidden reasoning/CoT не сохранять в Product timeline.
>
> Phase 6D stale acceptance hook не превращать в product feature. В ordinary runtime он disabled;
> temporary managed hook env/token после acceptance удалены.
>
> Light/white UI requirement остаётся debt и должен быть закрыт не позднее Phase 9,
> если пользователь не попросит раньше.

Следующий исполнитель после 7A должен вернуть:
- exact final 7A commit;
- доказательство `Start simulation → persisted event → automatic ADK investigation` без ручного user-facing `/agent/invoke`;
- описание dispatch/recovery/idempotency semantics и почему frontend не является agent orchestrator;
- Incidents list/detail realtime evidence;
- Observations list/detail realtime evidence;
- desktop wheel/trackpad + mobile touch scrolling evidence для overflow panels;
- Phase 6 Scenario 1 regression + frontend typecheck/lint/tests/build + Alembic/Docker status;
- PASS/PARTIAL только для 7A;
- baseline commit для 7B.