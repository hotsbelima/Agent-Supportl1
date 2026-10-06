# Autonomous L1 Incident Agent

## Canonical cumulative handoff v6.9 — Phase 7 DONE / PASS; Phase 8 NEXT

Дата: 6 октября 2026 года.

Этот файл — актуальная compact cumulative-точка входа проекта после полного **Phase 7 DONE / PASS**.

Он сохраняет без отката канонический boundary `ADK owns / Product owns`, результаты Phase 0–6, полный Scenario 2 из Phase 7 и managed live evidence.

Текущая точка остановки:

> **Phase 7 = DONE / PASS. Phase 8 = NEXT.**

---

## 1. Canonical baseline

Repository:

`hotsbelima/Agent-Supportl1`

Final Phase 7 development branch:

`phase-7d-scenario2-tools-hitl`

Final Phase 7 **code/live baseline**:

`2f8dae61c06afd0f134c58e90aba0591a013a31e`

Важно:

- этот SHA — immutable code baseline, на котором прошли deterministic Phase 7D gates и managed live Phase 7E;
- handoff-файл добавляется отдельным docs-only commit поверх него;
- при проверке runtime/code behavior ориентироваться именно на `2f8dae61...`, если docs-only commit не содержит изменений приложения.

Final deterministic GitHub Actions:

`37399813681` — SUCCESS

Managed Product API, использованный в Phase 7E:

`https://p01--product-api--yxz5y8myjdln.code.run/`

Alembic head:

`20261006_0006`

---

## 2. Как пользоваться этим handoff

При конфликте информации приоритет:

1. этот cumulative handoff v6.9;
2. repository code на final Phase 7 code baseline `2f8dae61c06afd0f134c58e90aba0591a013a31e`;
3. `docs/phase7d_implementation_notes.md`;
4. `docs/phase7c_adk_dispatch_completion.md`;
5. `docs/phase7c_product_ingestion_handoff.md`;
6. `docs/phase7b_scenario2_spec.md`;
7. предыдущий cumulative handoff v6.7 для истории Phase 0–6;
8. более ранние contracts/handoff — только для history/rationale.

Следующий исполнитель **не должен перепроектировать Phase 0–7** без воспроизводимого дефекта или подтверждённого ограничения Google ADK/Product architecture.

После каждого major checkpoint:

- фиксировать exact final commit;
- фиксировать CI/live evidence;
- не объявлять PASS только потому, что unit tests green;
- не менять ownership boundary без конкретного доказанного технического основания;
- сохранять regression Scenario 1 и Scenario 2 как обязательный safety net.

---

## 3. Краткий статус roadmap

| Фаза | Статус | Результат |
| --- | --- | --- |
| 0 | **DONE** | Architecture, Scenario 1, fixture/world truth, evidence/approval semantics. |
| 1 | **DONE** | Local Google ADK/Gemini two-tool spike. |
| 2 | **DONE** | Managed ADK/Gemini spike. |
| 3 | **DONE / PASS** | Product domain/contracts, validators, evidence, approval/execution boundary. |
| 4 | **DONE / PASS** | PostgreSQL persistence, lifecycle/events, Product API, managed backend. |
| 5 | **DONE / PASS** | Persisted SSE + operational UI + reload/reconnect/recovery + managed acceptance. |
| 6 | **DONE / PASS** | Native Google ADK runtime + complete Scenario 1 live vertical slice. |
| 7A | **DONE / PASS** | Automatic Product event → durable native ADK dispatch; operational UI restructuring. |
| 7B | **DONE / PASS** | Exact Scenario 2 spec + typed Product/domain contracts. |
| 7C | **DONE / PASS** | Product event ingestion + same-session multi-invocation ADK continuity + restart/redelivery. |
| 7D | **DONE / PASS** | Scenario 2 Product tools + evidence-backed Major Incident correlation + native HITL. |
| 7E | **DONE / PASS** | Managed live Scenario 2 happy/stale/restart/replay acceptance with real Gemini/ADK. |
| 7 | **DONE / PASS** | Full Scenario 2 live vertical slice. |
| 8 | **NEXT** | Scenario 3: disconfirmed hypothesis → replanning → new tool sequence. |
| 9 | **PLANNED** | Polish/hardening/public deploy; light/white UI debt must be closed no later than here. |

---

## 4. Цель продукта

Проект — демонстрационный **Autonomous L1 Incident Agent** для ITSM.

Он должен показывать практический опыт создания реально действующего агента:

- tool calling;
- persistent state;
- actions;
- guardrails;
- approvals;
- event-driven behavior;
- recovery/replay/idempotency;
- понятный бизнес-кейс.

Mock scenarios:

1. локальная проблема терминала → onsite Field Service proposal;
2. массовый сбой → Major Incident proposal;
3. неверная гипотеза опровергается evidence → replanning и новая tool sequence.

Реальных production ServiceNow/Zabbix/CMDB/1C mutations нет. Используются deterministic fixture/source-system adapters.

---

## 5. Каноническая архитектура после Phase 7

```text
Next.js operational UI
        │
        ├── HTTPS Product API
        └── persisted SSE
                │
                ▼
FastAPI product_api
        │
        ├── Product application/domain
        ├── persisted Product events / evidence / approvals / executions
        ├── durable outbox / dispatch
        ├── Scenario 1 Product services
        ├── Scenario 2 Product services
        │
        └── PostgreSQL 16
                │
                ├── Product tables
                └── native ADK persistence tables
                         │
                         ▼
                 Google ADK Runner
                         │
                         ├── persistent ADK Session
                         ├── native ADK Events
                         ├── FunctionTool
                         └── LongRunningFunctionTool
                                  │
                                  ▼
                              Gemini
```

### ADK owns

Google ADK остаётся владельцем generic agent-runtime mechanics:

- `Session`;
- native ADK `Events`;
- invocation lifecycle;
- model/tool-call lifecycle;
- persistent agent history;
- resumability;
- native long-running function pause/resume.

Для Product Run используется одна persistent native ADK Session:

`session_id = run_id`

`user_id = tenant_id`

`app_name = autonomous-l1-incident-agent`

### Product owns

Product остаётся владельцем business/operational truth:

- Run;
- Incident / ServiceIncident;
- operational signals;
- typed Evidence;
- Product application events/timeline;
- proposals;
- approvals;
- Major Incident execution;
- WorkOrder/Scenario 1 execution;
- tenant/run isolation;
- business idempotency;
- source-system adapters;
- Product API/SSE/UI.

**Incoming business event всегда сначала persist Product-side, затем dispatch к агенту.**

Hidden model reasoning / chain-of-thought **не копируется** в Product timeline.

Human Approve/Reject — Product application operation, а не model tool.

Нельзя создавать рядом с ADK второй generic session/runtime/resume framework.

---

# 6. Phase 6 — retained baseline

Phase 6 полностью закрыла Scenario 1 и исправила ownership generic runtime в пользу native Google ADK.

Final Phase 6 code baseline:

`919f7a61c9b7d390890de65cd94cd15452ef5aff`

Ключевой результат:

- native persistent ADK Session;
- six Scenario 1 Product tools;
- model-driven dependent tool calling;
- Product proposal;
- native `await_human_decision`;
- Product Approve/Reject/revalidation;
- same-invocation resume;
- restart/replay/stale acceptance;
- no duplicate custom agent runtime.

Phase 7 **не переписывала** этот runtime, а добавила Scenario 2 поверх него.

---

# 7. Phase 7 — DONE / PASS — Scenario 2

## 7A — DONE / PASS — durable automatic dispatch

Phase 7A добавила automatic operational event → agent dispatch поверх Product persistence.

Ключевые свойства:

- Product event persist before agent invocation;
- durable outbox;
- automatic worker;
- `operational_event_id` correlation;
- one Product Run ↔ one persistent ADK Session;
- hidden compatibility invoke route не является product interaction surface;
- Scenario 1 regression сохранён.

---

## 7B — DONE / PASS — Scenario 2 spec/contracts

Final PASS commit:

`a7e83f04c1cd5ac419bbe032c0c1c254ac763854`

Canonical Scenario 2 fixture:

Service:

`payment_gateway`

Correlation key:

`payment_gateway_timeout`

External dependency:

- ID: `DEP-ACMEPAY-PAYMENTS`
- name: `AcmePay`
- type: external provider
- initial status: `DEGRADED`

Sites:

- `SITE-KZN-017`
- `SITE-SAM-024`

Service incidents:

- `INC-S2-KZN-001`
- `INC-S2-SAM-001`

Canonical operational signals:

1. `SIG-S2-001`
   - source: MONITORING
   - site: `SITE-KZN-017`
   - source ref: `MON-ALERT-KZN-901`

2. `SIG-S2-002`
   - source: ITSM
   - site: `SITE-KZN-017`
   - source ref: `TICKET-KZN-5521`

3. `SIG-S2-003`
   - source: MONITORING
   - site: `SITE-SAM-024`
   - source ref: `MON-ALERT-SAM-337`

Signal payloads **не раскрывают AcmePay как готовый вывод**.

Hidden fixture truth:

- local network/service healthy at both sites;
- `payment_gateway` maps to AcmePay;
- AcmePay initially DEGRADED;
- matching open Major Incident initially absent.

Scenario 2 использует отдельный `ServiceIncident`, а не Scenario 1 device Incident.

---

## 7C — DONE / PASS — ingestion, persistence, same-session continuity

Final PASS commit:

`e8f4e667e2ba8f3d7223cf25897f72fcc115e699`

Live acceptance GitHub Actions:

`37394801698` — SUCCESS

Live Run / ADK Session:

`RUN-61c3fe1c950f4009b3ebfc0076688c75`

Product events:

1. `EVENT-9e1f530c84d046a4a3cd2a4f3f4078d5`
2. `EVENT-6a40d990e3bf48b1b4d8bad2c1c26aab`
3. `EVENT-d40fb5faefd2401db574ac44571a1044`

ADK invocation IDs:

1. `e-403eb2bf-3ffa-4c16-95b8-37769ba3e485`
2. `e-a5263537-3c43-4c81-adef-01389e5e8c5d`
3. `e-0dbd9356-bf9d-43dd-b727-6a06c5cb96cb`

Доказано:

- три persisted Product events;
- три independent native ADK invocations;
- одна persistent native ADK Session;
- `session_id == run_id`;
- restart continuity;
- forced redelivery event 1;
- redelivery не создала второй independent invocation;
- first event attempt count = 2;
- до Phase 7D никаких premature MI/proposal side effects.

### Canonical 7C correlation semantics

- event 1: persist → invocation 1;
- event 2: persist → invocation 2 same Session;
- event 3+: subsequent invocation same Session;
- Product signal state independent of ADK history;
- restart preserves Product facts + ADK Session continuity;
- первый single-site alert не доказывает Major Incident;
- второй same-site signal усиливает локальную проблему, но не является cross-site proof;
- independent second site разрешает investigation common dependency;
- correlation строится на persisted events + tool evidence;
- запрещено `if event_count >= N: propose_major_incident`.

---

## 7D — DONE / PASS — Scenario 2 tools + Major Incident HITL

Final Phase 7 code baseline:

`2f8dae61c06afd0f134c58e90aba0591a013a31e`

Scenario 2 native ADK tool surface:

1. `get_local_service_health`
2. `get_service_dependencies`
3. `get_external_dependency_status`
4. `search_major_incidents`
5. `propose_major_incident`

Первые четыре tool создают typed Product Evidence.

`propose_major_incident` создаёт только Product proposal `PENDING_APPROVAL`.

После successful proposal агент обязан вызвать native:

`await_human_decision`

Используется тот же ADK `LongRunningFunctionTool`/resume architecture, который был проверен Scenario 1.

### Major Incident persistence

Migration:

`20261006_0006`

Таблицы:

- `major_incident_proposals`
- `major_incident_approvals`
- `major_incidents`
- `major_incident_executions`

Equivalent Major Incident uniqueness tenant-wide по:

`(service_key, correlation_key, dependency_id)`

Public Product operations:

- `POST /api/v1/scenario-2/runs/{run_id}/proposals/{proposal_id}/approve`
- `POST /api/v1/scenario-2/runs/{run_id}/proposals/{proposal_id}/reject`

Approve:

1. Product decision commits;
2. Product повторно проверяет authoritative current truth;
3. только после успешной revalidation создаётся Major Incident execution;
4. затем резюмируется exact native ADK invocation.

Если truth изменился, proposal становится `STALE`, execution не создаётся.

### 7D hardening found during review

Во время отдельного verification pass были найдены и исправлены реальные дефекты:

- Scenario 2 runtime подключён к существующему `ProductRetryableToolPlugin`;
- `await_human_decision` принимается только после реального successful `propose_major_incident`;
- proposal без native wait считается non-recoverable;
- delivered FunctionResponse очищает pending-wait state;
- исправлен FK ordering при создании `MajorIncidentRecord` + dependent execution;
- сохранена compatibility с sparse historical Phase 7C ADK events;
- health/public contracts сделаны additive, а не ломающими предыдущие checkpoint expectations.

Final deterministic gate на exact code baseline:

- focused Phase 7D: **9 passed**;
- Alembic: `20261006_0006 (head)`;
- Alembic autogenerate check: clean;
- full Python regression: **195 passed**;
- retained Node regression: PASS;
- frontend tests: **42 passed**;
- frontend typecheck/lint/build: PASS;
- static audit: PASS;
- Docker Product image: PASS.

GitHub Actions:

`37399813681` — SUCCESS

---

## 7E — DONE / PASS — managed live acceptance

Phase 7E выполнена на managed deployment с **реальным Gemini + Google ADK**.

Код после final 7D baseline не менялся.

### Managed happy path

Run:

`RUN-06fdfea4c7e945af9495d2faedc9987e`

Native ADK Session:

`RUN-06fdfea4c7e945af9495d2faedc9987e`

Product events → ADK invocations:

| Product event | ADK invocation |
| --- | --- |
| `EVENT-1efe89aa59694284b073366c99c04cae` | `e-650ee2d2-5007-48f1-950f-c31822ee829d` |
| `EVENT-34acfdd1c707484799c72c36083e3395` | `e-7dc7aabe-f5b0-4b23-83da-a4bfea5270c6` |
| `EVENT-df8fd6441a794f699c1c655bbbd10984` | `e-4e5674ac-e2e4-4e62-9fd3-715e5c6cb6de` |

Доказано:

- после event 1 proposal отсутствует;
- после event 2 proposal отсутствует;
- на independent-site event 3 агент начинает common dependency investigation;
- использованы все пять Scenario 2 tools;
- Product evidence подтверждает local HEALTHY на обоих sites;
- dependency mapping подтверждает AcmePay;
- external dependency status подтверждает `DEGRADED`;
- duplicate MI search подтверждает отсутствие matching open MI;
- proposal использует реальные persisted Evidence IDs.

Managed process был перезапущен между event 2 и event 3.

После restart:

- Product facts сохранились;
- native Session сохранилась;
- event 3 продолжил тот же `session_id == run_id`.

Proposal:

`MI-PROPOSAL-19e973b0264a40f3bee93d85d3bc45fc`

Native HITL pause:

- invocation: `e-4e5674ac-e2e4-4e62-9fd3-715e5c6cb6de`
- function call: `call_22923`

Approval:

`MI-APPROVAL-067049b12a9d4068b5f029dae94183bd`

Major Incident:

`MAJOR-INCIDENT-0917711847f64fbe9547c6cbaccd5235`

Execution:

`MI-EXECUTION-98cf0818eed448d6a91cd7efa3964eda`

Approve:

- Product revalidated current truth;
- proposal → `EXECUTED`;
- создан ровно 1 Major Incident;
- создан ровно 1 execution;
- тот же native invocation resumed;
- повторный Approve вернул `replayed=true`;
- duplicate MI/execution не появились.

### Managed stale path

Run:

`RUN-1acbd91e40934fcbb3856a918db12b81`

Native Session ID совпадает с Run ID.

После создания `PENDING_APPROVAL` штатный Scenario 2 fixture transition изменил:

`AcmePay DEGRADED → HEALTHY`

После Approve:

- Product revalidation увидела изменившуюся truth;
- proposal → `STALE`;
- `MajorIncidentExecution` не создан;
- Major Incident не создан;
- native ADK resumed same invocation:

`e-bb92aafc-9ff9-446b-9514-4e0f244d6212`

Все три outbox rows были доставлены.

### Phase 7E final decision

> **Phase 7E = DONE / PASS**
>
> **Phase 7 = DONE / PASS**

Подтверждённых code defects после финального live acceptance не обнаружено.

---

## 8. Phase 7 hard invariants — сохранить дальше

Не считать архитектуру корректной, если в будущих изменениях нарушено хоть одно:

1. Incoming event сначала persisted Product-side.
2. Один Product Run использует одну persistent native ADK Session.
3. Каждый новый business event может запускать отдельный invocation той же Session.
4. Product business truth не переносится в generic ADK state.
5. ADK native Events не копируются целиком в Product timeline.
6. Hidden CoT/reasoning не попадает в Product persistence/UI.
7. Model не выбирает `tenant_id` / `run_id`.
8. Cross-site correlation не hard-coded по event count/order.
9. Common dependency должна подтверждаться Product tool evidence.
10. Major Incident не создаётся до human approval.
11. Approve всегда revalidates current source truth.
12. Retry/replay/concurrent decision не создаёт duplicate execution.
13. Restart не должен терять Product facts, ADK Session или pending native HITL correlation.
14. Не создавать второй generic agent-runtime/session/resume framework рядом с ADK.
15. Scenario 1 regression остаётся обязательным при изменениях Scenario 2/3.

---

## 9. Known limitations / debt

### Gemini quota

Во время live acceptance наблюдался provider limit:

**15 requests/minute**

Один ранний stale run столкнулся с Gemini `429` и ошибочным аргументом поиска от модели.

Повторный отдельный live run прошёл полностью.

Это считать known provider/model limitation, а не подтверждённым Product defect.

### Light/white UI

Ранее пользователь задавал требование **light/white UI**.

Phase 5 functional acceptance проходил на текущем dark UI, и пользователь решил не переоткрывать Phase 5.

Visual debt остаётся:

- не удалять из следующих handoff;
- закрыть при отдельном frontend polish;
- крайний срок — Phase 9, если пользователь не попросит раньше.

### Phase 6D acceptance hook

Исторический Phase 6D stale-acceptance hook был acceptance-only механизмом и **не должен превращаться в Product feature**.

Scenario 2 stale acceptance использует собственный controlled fixture transition, а не manual Product DB mutation.

---

# 10. Phase 8 — NEXT

Phase 8 по roadmap:

> **Scenario 3: disconfirmed hypothesis → replanning → new tool sequence**

High-level цель:

агент должен не только успешно пройти заранее очевидную цепочку tools, но и показать **корректное изменение плана**, когда первоначальная рабочая гипотеза опровергнута evidence.

Phase 8 должна строиться **поверх уже закрытых Phase 6/7 primitives**, а не создавать новый runtime.

Нужно сохранить:

- native persistent ADK Session/Events;
- Product-owned facts/evidence/guardrails;
- typed Product tools;
- durable dispatch;
- evidence-first decisions;
- Product human approval для side effects;
- restart/retry/replay safety.

До отдельной Phase 8 спецификации **не фиксировать заранее искусственный tool sequence** как implementation truth.

Следующий исполнитель сначала должен уточнить exact Scenario 3 fixture, initial hypothesis, disconfirming evidence, expected replanning behavior и acceptance criteria.

---

## 11. Быстрая проверка repository

Backend:

```bash
python -m pip install -r requirements.txt
python -m pip check
python -m pytest -q
npm test
```

PostgreSQL integration требует `DATABASE_URL`.

Migrations:

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

Product API:

```bash
python -m product_api
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

Canonical GitHub workflows используют PostgreSQL 16 service container.

---

# 12. Передача следующему исполнителю

Стартовая инструкция:

> Phase 0–7 закрыты.
>
> **Phase 7 = DONE / PASS**.
>
> Final live-validated Phase 7 code baseline:
>
> `2f8dae61c06afd0f134c58e90aba0591a013a31e`
>
> Не перепроектируй Product/ADK ownership и не создавай новый generic agent framework.
>
> Product PostgreSQL остаётся source of truth для business/operational state, Evidence, approvals и executions.
>
> Native Google ADK Session/Events остаются source of truth для generic agent-runtime continuity.
>
> Scenario 1 и Scenario 2 regressions обязательны.
>
> Следующая фаза — **Phase 8 / Scenario 3: disconfirmed hypothesis → replanning → new tool sequence**.
>
> Сначала зафиксируй exact Scenario 3 specification и acceptance criteria, затем режь её на implementation checkpoints.
>
> Не теряй known debt: light/white UI должен быть закрыт не позднее Phase 9.