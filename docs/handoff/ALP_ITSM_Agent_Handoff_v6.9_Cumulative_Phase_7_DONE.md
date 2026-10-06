# Autonomous L1 Incident Agent

## Canonical cumulative handoff v6.9 — Phase 7 DONE / PASS

Дата: 6 октября 2026 года.

Этот файл — новая **canonical point of entry** проекта после полного завершения Phase 7.
Он заменяет старый cumulative handoff v5.7 как актуальную точку входа и фиксирует
состояние проекта после live managed acceptance Scenario 2.

Старые handoff/contract документы сохраняются как история и evidence, но если их
статус расходится с этим документом и текущим репозиторием, приоритет такой:

1. фактический код и migration state репозитория;
2. этот cumulative handoff;
3. phase-specific implementation notes / contracts;
4. старые cumulative handoff и README.

> Важно: verified product/code checkpoint Phase 7 —  
> `2f8dae61c06afd0f134c58e90aba0591a013a31e`.
>
> Этот handoff добавляется отдельным docs-only commit после live acceptance,
> поэтому Git branch HEAD может быть новее verified code SHA. Не путать docs-only
> commit с SHA managed deployment, на котором выполнен Phase 7E acceptance.

---

## 1. Текущий статус проекта

| Фаза | Статус | Результат |
| --- | --- | --- |
| 0. Architecture / Scenario 1 design | **DONE** | Зафиксированы архитектура, Scenario 1, evidence, approval semantics и roadmap. |
| 1. Local ADK/Gemini spike | **DONE / PASS** | Доказан dependent multi-step tool calling Google ADK + Gemini локально. |
| 2. Managed runtime spike | **DONE / PASS** | Тот же runtime доказан в managed environment. |
| 3. Product domain / contracts | **DONE / PASS** | Product-domain contracts, validators, evidence и approval/execution boundary. |
| 4. Persistence + Product API | **DONE / PASS** | PostgreSQL, repositories/UoW, Product API, managed DB/deploy acceptance. |
| 5. Persisted events/SSE + operational UI | **DONE / PASS** | Persisted timeline, reconnect/cursor semantics и operational console. |
| 6. Live Scenario 1 ADK integration | **DONE / PASS** | Native ADK persistence, six tools, HITL resume и full Scenario 1 E2E. |
| 7. Scenario 2 multi-event correlation + Major Incident HITL | **DONE / PASS** | Event-driven multi-site correlation, Product tools, native HITL, managed live acceptance. |
| 8. Scenario 3 replanning | **NEXT** | Disconfirmed hypothesis + replanning по новым evidence. Exact scope ещё не зафиксирован. |
| 9. Polish / hardening / public demo | **PLANNED** | Финальное product/demo hardening, документация и публичная подача. |

### Главный checkpoint

**Phase 7 закрыта полностью: 7A → 7B → 7C → 7D → 7E = DONE / PASS.**

Текущий verified code checkpoint:

- branch: `phase-7d-scenario2-tools-hitl`
- commit: `2f8dae61c06afd0f134c58e90aba0591a013a31e`
- GitHub Actions run: `37399813681` — **success**
- Alembic head: `20261006_0006`
- managed Product API: `https://p01--product-api--yxz5y8myjdln.code.run/`

---

## 2. Цель продукта

Проект — демонстрационный **Autonomous L1 Incident Agent** для ITSM.

Он должен показывать не чат с зашитым ответом, а реальный проверяемый agentic flow:

```text
operational event
  -> persisted Product fact
  -> durable dispatch
  -> native Google ADK invocation
  -> model-selected Product tools
  -> persisted Evidence
  -> evidence-backed decision/proposal
  -> human approval boundary
  -> deterministic Product execution
  -> native ADK resume
  -> audit-safe timeline/UI
```

Система намеренно использует deterministic mock/provider boundaries вместо
настоящих ServiceNow/Zabbix/CMDB. Ценность проекта — agent reasoning through tools,
state, evidence, guardrails, persistence, HITL, restart recovery и idempotency.

---

## 3. Актуальная архитектура

```text
Next.js operational UI (Vercel)
           |
        HTTPS/SSE
           |
FastAPI Product API / Northflank
           |
           +-- Product application/domain
           +-- PostgreSQL Product state
           +-- durable application outbox
           +-- Google ADK Runner
           +-- native ADK DatabaseSessionService
           +-- deterministic Scenario fixtures/providers
           |
        Gemini
```

### Базовые runtime pins

- Python: `3.12.14`
- Google ADK: `2.10.0`
- Gemini: `gemini-3.5-flash-lite`
- FastAPI: `0.141.1`
- Uvicorn: `0.54.0`
- pytest: `8.4.2`

### Ключевой ownership boundary

**Google ADK владеет:**

- Session;
- native Events;
- invocation lifecycle;
- model/tool loop;
- long-running function wait/resume;
- generic runtime resumability.

**Product layer владеет:**

- Run;
- operational signals/events как бизнес-фактами;
- incidents/service incidents;
- Evidence;
- proposal/approval/execution;
- business idempotency;
- tenant/run isolation;
- Product audit timeline/SSE/UI;
- deterministic revalidation перед опасным действием.

Product не строит второй generic agent framework поверх ADK.

### Product Run ↔ ADK Session

Для product runs действует deterministic mapping:

```text
ADK app_name   = autonomous-l1-incident-agent
ADK user_id    = Product tenant_id
ADK session_id = Product run_id
```

**Один Product Run = одна persistent native ADK Session.**

Для Scenario 2 каждый новый persisted operational event создаёт отдельный native
ADK invocation в той же Session.

### Human approval

Human Approve/Reject — **Product application operation**, а не LLM tool.

Native ADK используется только как pause/resume boundary:

```text
Product proposal PENDING_APPROVAL
  -> ADK await_human_decision LongRunningFunctionTool
  -> Product Approve/Reject API
  -> deterministic Product revalidation/execution
  -> committed Product result
  -> resume exact same ADK invocation
```

---

## 4. Неподвижные архитектурные правила

Следующие правила уже доказаны предыдущими фазами и не должны пересобираться без
технически доказанной причины:

- один основной ADK agent, без самописного generic orchestrator поверх ADK;
- Product state и ADK Session state не дублируют друг друга;
- incoming event сначала сохраняется Product-side, потом dispatch к агенту;
- simulator/ingestion создаёт факты, но не принимает correlation decision;
- запрещено `if event_count >= N: propose_major_incident`;
- решение агента должно опираться на persisted facts + typed Evidence;
- LLM не имеет прямого доступа к БД, secrets или mutation endpoints;
- tenant/run context не является model-visible аргументом tool;
- hidden reasoning / thought fields не копируются в Product timeline;
- approval не считается исполнением;
- Product повторно проверяет current truth перед approved execution;
- retry/replay не должен создавать duplicate proposal/action/work order/Major Incident;
- restart managed процесса не должен ломать Product state или native Session continuity;
- acceptance не проходит через ручное редактирование Product DB.

---

## 5. Scenario 1 — текущий baseline

Scenario 1 закрыт в Phase 6.

Он доказывает полный vertical slice для локального device/access-link incident:

- persistent Product Run;
- native ADK persistent Session;
- six Product tools;
- evidence-backed diagnosis;
- proposal Field Service;
- Product human approval/reject;
- native ADK wait/resume;
- deterministic execution;
- restart/replay/idempotency;
- operational UI/timeline.

Scenario 1 остаётся regression baseline. Scenario 2 не должен ломать его contracts
или reuse его field-visit tools как фальшивые Scenario 2 tools.

---

## 6. Phase 7 — Scenario 2: DONE / PASS

Цель Phase 7: доказать **multi-event correlation** на нескольких независимых
площадках и safe Major Incident HITL flow.

Canonical Scenario 2 fixture:

- business service: `payment_gateway`
- correlation/symptom: `payment_gateway_timeout`
- external dependency:
  - ID: `DEP-ACMEPAY-PAYMENTS`
  - name: `AcmePay`
  - initial status: `DEGRADED`
- sites:
  - `SITE-KZN-017`
  - `SITE-SAM-024`
- service incidents:
  - `INC-S2-KZN-001`
  - `INC-S2-SAM-001`

Canonical input sequence:

1. monitoring signal, KZN;
2. ITSM/same-site signal, KZN;
3. monitoring signal, independent SAM site.

Сами signal payloads не содержат готового ответа про AcmePay.

### 7A — event-driven Product dispatch / operational surface

**DONE / PASS.**

Добавлены durable Product dispatch semantics и operational event path.
Frontend не оркестрирует вызовы Gemini. Product outbox является delivery boundary.

### 7B — Scenario 2 spec + contracts

**DONE / PASS.**

Зафиксированы:

- `ServiceIncident`;
- `OperationalSignal`;
- provider-neutral source ports;
- Scenario 2 tool contracts;
- Major Incident proposal/approval/execution domain rules;
- deterministic fixture/world truth;
- запрет premature cross-site escalation.

Основной spec:

- `docs/phase7b_scenario2_spec.md`

### 7C — multi-event ingestion + native ADK continuity

**DONE / PASS.**

Verified code checkpoint Phase 7C:

- commit: `e8f4e667e2ba8f3d7223cf25897f72fcc115e699`

Доказано:

- каждый persisted Scenario 2 event создаёт отдельный native invocation;
- все invocations используют одну persistent Session;
- `session_id == run_id`;
- process restart сохраняет Product + ADK continuity;
- outbox redelivery не создаёт второй independent invocation;
- первые два same-site events не создают Major Incident proposal.

Phase 7C live run:

- Product run / native session:
  `RUN-61c3fe1c950f4009b3ebfc0076688c75`
- forced redelivery event 1: 2 attempts, без duplicate invocation.

Документы:

- `docs/phase7c_product_ingestion_handoff.md`
- `docs/phase7c_adk_dispatch_completion.md`

### 7D — Scenario 2 Product tools + Major Incident HITL

**DONE / PASS.**

Добавлены пять model-visible Product tools:

1. `get_local_service_health`
2. `get_service_dependencies`
3. `get_external_dependency_status`
4. `search_major_incidents`
5. `propose_major_incident`

Четыре read tools сохраняют typed Product Evidence.

`propose_major_incident` создаёт только `PENDING_APPROVAL` proposal и требует
evidence-backed картины:

- cross-site signals минимум для двух независимых sites;
- local network/service HEALTHY на affected sites;
- service → external dependency mapping;
- external dependency DEGRADED;
- fresh negative matching-Major-Incident search.

Migration `20261006_0006` добавляет:

- `major_incident_proposals`
- `major_incident_approvals`
- `major_incidents`
- `major_incident_executions`

Product endpoints:

- `POST /api/v1/scenario-2/runs/{run_id}/proposals/{proposal_id}/approve`
- `POST /api/v1/scenario-2/runs/{run_id}/proposals/{proposal_id}/reject`

Hardening, найденный во время 7D review:

- подключён existing `ProductRetryableToolPlugin`;
- native wait принимается только после реального успешного proposal и с exact proposal ID;
- proposal без native wait не считается recoverable/delivered;
- FunctionResponse корректно завершает pending-wait state;
- исправлен FK insert order для Major Incident → Execution;
- сохранена backward compatibility с sparse historical ADK events из 7C;
- duplicate Major Incident protection tenant-wide.

Deterministic gate Phase 7D:

- focused 7D: **9 passed**
- full Python: **195 passed**
- frontend: **42 passed**
- Alembic: `20261006_0006 (head)`, clean check
- Node regression: PASS
- frontend typecheck/lint/build: PASS
- static audit: PASS
- Product Docker build: PASS

Implementation notes:

- `docs/phase7d_implementation_notes.md`

### 7E — managed/live acceptance

**DONE / PASS.**

Live acceptance выполнен на managed deployment с реальными Gemini и Google ADK.

Verified deployment code:

- branch: `phase-7d-scenario2-tools-hitl`
- commit: `2f8dae61c06afd0f134c58e90aba0591a013a31e`
- GitHub Actions: run `37399813681` — success
- Alembic: `20261006_0006`
- Product API:
  `https://p01--product-api--yxz5y8myjdln.code.run/`

#### Happy path evidence

Product Run / native ADK Session:

`RUN-06fdfea4c7e945af9495d2faedc9987e`

| Product event | Native ADK invocation |
| --- | --- |
| `EVENT-1efe89aa59694284b073366c99c04cae` | `e-650ee2d2-5007-48f1-950f-c31822ee829d` |
| `EVENT-34acfdd1c707484799c72c36083e3395` | `e-7dc7aabe-f5b0-4b23-83da-a4bfea5270c6` |
| `EVENT-df8fd6441a794f699c1c655bbbd10984` | `e-4e5674ac-e2e4-4e62-9fd3-715e5c6cb6de` |

После первых двух сигналов proposal отсутствовал.

На третьем event агент реально использовал все пять Scenario 2 tools и Product
сохранил evidence для:

- HEALTHY local state обоих sites;
- зависимости на AcmePay;
- AcmePay = DEGRADED;
- отсутствия matching open Major Incident.

Managed process был перезапущен между вторым и третьим event.
После restart третий event продолжил **ту же native Session**.

HITL evidence:

- proposal:
  `MI-PROPOSAL-19e973b0264a40f3bee93d85d3bc45fc`
- paused invocation:
  `e-4e5674ac-e2e4-4e62-9fd3-715e5c6cb6de`
- native wait function call:
  `call_22923`
- approval:
  `MI-APPROVAL-067049b12a9d4068b5f029dae94183bd`
- Major Incident:
  `MAJOR-INCIDENT-0917711847f64fbe9547c6cbaccd5235`
- execution:
  `MI-EXECUTION-98cf0818eed448d6a91cd7efa3964eda`

Approve повторно проверил current Product truth, создал ровно один Major Incident
и один execution, затем возобновил **тот же invocation**.

Повторный Approve вернул `replayed=true` с теми же IDs, без дублей.

#### Stale path evidence

Отдельный Product Run / native Session:

`RUN-1acbd91e40934fcbb3856a918db12b81`

После создания proposal штатный fixture transition изменил:

```text
AcmePay DEGRADED -> HEALTHY
```

Затем был выполнен Approve.

Результат:

- proposal -> `STALE`;
- Major Incident не создан;
- execution не создан;
- Product committed stale result;
- native ADK возобновил тот же invocation:
  `e-bb92aafc-9ff9-446b-9514-4e0f244d6212`;
- все три outbox entries доставлены.

#### Ограничение, обнаруженное в live acceptance

Подтверждённых дефектов кода после финального прогона не осталось.

Один более ранний stale-run столкнулся с:

- Gemini 429;
- ошибочным аргументом search tool со стороны модели.

Новый независимый live acceptance прошёл полностью.

Текущее известное operational limitation: Gemini quota около **15 requests/min**
может замедлять или обрывать повторные acceptance runs. Это не считается
дефектом Product architecture.

---

## 7. Физический результат после Phase 7

На текущем checkpoint проект уже демонстрирует два полноценных agentic сценария:

### Scenario 1

Single-incident diagnosis → evidence → Field Service proposal → human decision →
deterministic execution → native ADK resume.

### Scenario 2

Multiple persisted events → one persistent ADK Session → independent invocations →
model-selected Product tools → cross-site evidence correlation → Major Incident
proposal → native HITL → Product revalidation → execute or STALE → same-invocation resume.

Проект теперь демонстрирует:

- tool calling;
- state across events;
- persistent sessions;
- durable event delivery;
- retries/redelivery;
- evidence;
- deterministic guardrails;
- human approval;
- restart recovery;
- idempotency;
- stale-world revalidation;
- auditability;
- managed live execution с реальным Gemini.

---

## 8. Что НЕ нужно переделывать в Phase 8

Phase 8 не является поводом переписывать уже доказанную платформу.

Без доказанной необходимости нельзя:

- заменять native ADK Session собственным session framework;
- делать новый custom agent loop;
- переносить correlation/replanning decision в ingestion backend;
- давать LLM прямой доступ к Product DB;
- превращать Product approval в model tool;
- убирать durable outbox;
- копировать hidden model reasoning в timeline;
- ломать `session_id == run_id`;
- переносить business idempotency в LLM prompt;
- hard-code очередность выводов по event number.

Phase 8 должна по возможности **переиспользовать** уже построенные:
Product state, Event/Outbox, Evidence, tool adapter boundary, native ADK lifecycle,
persistent Session, approval framework и UI/timeline.

---

## 9. Phase 8 — NEXT

High-level roadmap из исходного проекта:

**Scenario 3 — disconfirmed hypothesis + replanning по новым evidence.**

На момент этого handoff детальный Phase 8 implementation contract ещё не
зафиксирован. Это намеренно.

Перед кодом Phase 8 нужно сначала определить:

1. точный Scenario 3 fixture/world truth;
2. initial hypothesis и какие evidence делают её правдоподобной;
3. новое evidence, которое её опровергает;
4. какой новый plan/tool sequence агент должен выбрать после опровержения;
5. какие Product tools можно переиспользовать, а какие действительно нужны новые;
6. какие state/evidence invariants Product должен проверять независимо от LLM;
7. exact acceptance criteria для replanning;
8. managed/live acceptance criteria.

Phase 8 нельзя начинать с абстрактного «добавить replanning».
Сначала спецификация, затем implementation slices.

---

## 10. Документы, с которых начинать следующий чат

### Canonical

- **этот файл**:
  `docs/handoff/ALP_ITSM_Agent_Handoff_v6.9_Cumulative_Phase_7_DONE.md`

### Phase 7 evidence/spec

- `docs/phase7b_scenario2_spec.md`
- `docs/phase7c_product_ingestion_handoff.md`
- `docs/phase7c_adk_dispatch_completion.md`
- `docs/phase7d_implementation_notes.md`

### Архитектурные contracts предыдущих фаз

- `docs/contracts/PHASE_3_DOMAIN_AND_TOOL_CONTRACTS.md`
- `docs/contracts/PHASE_4A_POSTGRES_PERSISTENCE.md`
- `docs/contracts/PHASE_4B_PERSISTED_LIFECYCLE.md`
- `docs/contracts/PHASE_4C_PRODUCT_API.md`
- `docs/contracts/PHASE_6A_NATIVE_ADK_PERSISTENCE.md`
- `docs/contracts/PHASE_6B_NATIVE_SIX_TOOL_ADK.md`
- `docs/contracts/PHASE_6C_HUMAN_DECISION_RESUME.md`

Старый `ALP_ITSM_Agent_Handoff_v5.7_Cumulative.md` теперь исторический и не
должен использоваться как актуальный roadmap.

---

## 11. Правило документации дальше

Чтобы история проекта снова не расползалась по чатам:

- после каждой **подфазы** сохранять короткие Implementation Notes / delta;
- после каждой **крупной фазы** обновлять canonical cumulative handoff;
- в handoff всегда фиксировать exact branch/SHA и PASS/PARTIAL/NEXT;
- runtime/live PASS фиксировать отдельно от «код написан»;
- repository reality имеет приоритет над памятью чата.

---

## 12. Точка передачи

**Текущее состояние:**

```text
Phase 7 = DONE / PASS
Scenario 1 = implemented + live validated
Scenario 2 = implemented + managed live validated
Current verified product SHA = 2f8dae61c06afd0f134c58e90aba0591a013a31e
Alembic head = 20261006_0006
Next major phase = Phase 8 / Scenario 3 replanning
```

Следующий исполнитель должен начать не с изменения кода, а с подготовки
**точной Phase 8 specification + acceptance criteria** поверх этого baseline.
