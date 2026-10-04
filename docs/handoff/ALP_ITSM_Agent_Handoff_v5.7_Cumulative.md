# Autonomous L1 Incident Agent

## Canonical cumulative handoff v5.7

Дата: 4 октября 2026 года. Этот файл — единый актуальный handoff проекта.
Он обновляет cumulative handoff v5.6 после полного аудита Фазы 3, сохраняет
все принятые архитектурные и сценарные решения и фиксирует следующий этап как
**Фазу 4 — Persistent application backend foundation**.

### Как теперь ведём handoff

После каждой фазы публикуются **два** документа:

1. короткий *delta update* — что именно изменилось в этой фазе, с командами,
   trace и результатами проверок;
2. новый (или обновлённый) *cumulative handoff* — самостоятельная накопительная
   картина всего проекта на текущий момент.

Delta — журнал изменений и доказательства. Cumulative handoff — единственная
точка входа для человека, который подключается к проекту позже. Нельзя вместо
него отдавать только delta.

| Документ | Роль |
| --- | --- |
| `ALP_ITSM_Agent_Handoff_v5.3_Final_Sanity_Checked.md` | исходный согласованный baseline (вне репозитория) |
| `ALP_ITSM_Agent_Handoff_v5.4_Phase_1_Update.md` | delta Фазы 1 |
| `ALP_ITSM_Agent_Handoff_v5.5_Phase_2_Update.md` | delta Фазы 2 |
| `ALP_ITSM_Agent_Handoff_v5.6_Phase_3_Update.md` | delta Фазы 3 |
| **этот файл** | актуальный накопительный handoff v5.7; Phase 4 kickoff |

## Краткий статус

| Фаза | Статус | Что означает |
| --- | --- | --- |
| 0. Архитектура и design package Scenario 1 | завершена | зафиксированы границы, fixture, evidence и approval semantics |
| 1. Local ADK/Gemini spike | завершена | Gemini локально трижды построил зависимую цепочку двух tools |
| 2. Managed runtime spike | завершена в узком runtime scope | тот же агент трижды прошёл на Northflank с секретом вне локальной машины |
| 3. Product contracts и domain foundation | завершена | отдельный product-domain, validators, approval boundary и six-tool adapter integration прошли regression |
| 4. Persistent application backend foundation | следующая / не начата | PostgreSQL, concrete repositories/UoW, persisted audit/events и product lifecycle/approval API; без UI и live ADK wiring |

## Общий roadmap проекта

Это **каноническая верхнеуровневая дорожная карта всего проекта**. Она нужна,
чтобы новый исполнитель видел не только следующий шаг, но и конечную
последовательность разработки. Завершённые фазы не пересматриваются без
технически доказанной причины. Для будущих фаз high-level scope фиксирован
здесь, а детальный implementation contract уточняется непосредственно перед
началом соответствующей фазы.

| Фаза | Название | Статус | Верхнеуровневый результат |
| --- | --- | --- | --- |
| **0** | Architecture / design | **DONE** | Зафиксированы архитектура, Scenario 1, fixture/world truth, evidence/approval semantics и общий product scope. |
| **1** | Local ADK/Gemini runtime spike | **DONE** | Локально доказан реальный dependent multi-step tool calling на Google ADK + Gemini. |
| **2** | Managed runtime spike | **DONE** | Тот же runtime и dependent tool calling доказаны вне локальной машины на Northflank. |
| **3** | Product domain / contracts | **DONE** | Построены product-domain contracts, evidence validation, ownership/state rules, approval/execution boundary и six-tool integration layer. |
| **4** | Persistence + application backend | **NEXT** | PostgreSQL, concrete repositories/UoW, persisted audit/events, product lifecycle API и human approval API. |
| **5** | Persisted SSE + operational UI | **PLANNED** | Persisted event stream с cursor/reconnect и operational console для run timeline, agent activity, incident/evidence/proposal/approval state. |
| **6** | Live six-tool Google ADK integration + Scenario 1 E2E | **PLANNED** | Все шесть Scenario 1 tools реально подключены к Google ADK; полный headless/UI vertical slice проходит end-to-end до approval/execution. |
| **7** | Scenario 2 | **PLANNED** | Multi-event correlation, внешний dependency check и Major Incident proposal/approval flow. |
| **8** | Scenario 3 | **PLANNED** | Disconfirmed hypothesis, replanning и новая последовательность tools по новым evidence. |
| **9** | Polish, hardening, public deploy | **PLANNED** | Error/empty states, reset/scenario selector, security/observability hardening, финальная документация, архитектурная схема и публичный demo deploy. |

### Правило детализации roadmap

- Фазы **0–3** закрыты и считаются baseline.
- Фаза **4** уже имеет детализированный scope ниже в этом handoff.
- Фазы **5–9** сейчас зафиксированы именно как high-level roadmap.
- Перед стартом каждой из Фаз 5–9 создаётся её собственный точный scope и
  acceptance criteria.
- Нельзя тащить задачи будущей фазы в текущую только потому, что они
  технически уже возможны.
- Если техническое ограничение действительно ломает roadmap, сначала
  фиксируется причина и обновляется cumulative handoff, и только затем
  меняется реализация.


**Главный вывод:** выбранный runtime жизнеспособен: Python 3.12.14, Google ADK
2.10.0 и `gemini-3.5-flash-lite` смогли в реальных прогонах сами выбрать
`get_device`, извлечь из результата `attachment_id` и передать его в
`run_diagnostic`. Это подтверждено и локально, и на Northflank.

Теперь создана устойчивая **headless domain foundation Scenario 1**: contracts,
evidence validation, proposal/approval semantics и concrete tool-adapter
boundary. Но готового демонстрационного backend/UI ещё нет: PostgreSQL,
product API, persisted events/SSE, UI и live six-tool ADK wiring пока
намеренно не строились.

## Цель продукта

Проект — демонстрационный Autonomous L1 Incident Agent для ITSM-процесса.
Он должен показать не чат с зашитым ответом, а расследование: агент получает
операционный сигнал, выбирает разрешённые read-only tools, собирает evidence,
формирует ограниченное proposal там, где нужен человек, и не имитирует
исполнение до approval.

В целевой демо-версии три mock-сценария:

1. локальная проблема терминала и предложение onsite Field Service;
2. массовый сбой и proposal Major Incident;
3. пересмотр неверной гипотезы VPN/DNS по новым evidence.

Нет реальных ServiceNow, Zabbix, CMDB или производственных действий. Их роли
воспроизводятся контролируемым mock-доменом и adapter boundaries. Ценность
демо — проверяемая логика, audit trail, безопасность и честные ограничения,
а не видимость подключения к чужим системам.

## Принятая архитектура

Целевой продукт — **modular monolith**:

```text
Next.js UI (Vercel) ── HTTPS/SSE ── FastAPI application (Northflank)
                                        │
                                        ├─ application/domain layer
                                        ├─ Google ADK agent + function-tool adapters
                                        ├─ PostgreSQL (runs, events, proposals, approvals)
                                        └─ deterministic simulator / fixture world
```

- Один ADK agent, а не набор агентов и не orchestrator поверх них.
- Один FastAPI backend владеет run, domain state, events, proposals и
  approval boundary.
- ADK владеет историей и состоянием agent session; приложение не пишет в его
  внутренние таблицы и не копирует session state в «универсальную память».
- Один simulation run соответствует одной ADK session и нескольким
  последовательным обращениям. Внутри run нет конкурентных вызовов агента.
- PostgreSQL появится для продуктового состояния; он не создан в spike.
- UI отображает факты, tool actions, краткие выводы и approval state, но не
  chain-of-thought модели.
- SSE будет отдавать уже сохранённые application events с курсором для
  переподключения. Это будущая продуктовая функция, не часть текущего spike.

### Разделение ответственности

| Слой | За что отвечает |
| --- | --- |
| Fixture/simulator | мир сценария, initial events, скрытый ground truth, детерминированные наблюдения |
| Agent | выбирает гипотезы, tools и их порядок, формулирует вывод и proposal |
| Tool adapters | узкий model-visible schema, thin delegation в application/domain path, нормализованный result |
| Domain layer | pure read-model rules, tenant/run/ID invariants, TTL validation, state transitions, duplicates и допустимость action |
| Application/API | lifecycle run, persistence, SSE, human endpoints, idempotency и auth |
| Human | approve/reject затратного или рискованного action |

LLM не является источником истины и не получает прямой доступ к БД, секретам,
approval endpoint, mutation API или скрытому fixture answer. Умение модели
планировать не отменяет contracts: они определяют, что tool может принять,
вернуть и изменить, а также что обязательно проверяется независимо от текста
модели.

## Зафиксированный runtime и граница текущего spike

| Компонент | Значение |
| --- | --- |
| Python | `3.12.14` |
| Google ADK | `2.10.0` |
| Gemini model | `gemini-3.5-flash-lite` |
| FastAPI | `0.141.1` |
| Uvicorn | `0.54.0` |
| Test runner | `pytest==8.4.2` |

Текущий код находится в `phase1_adk_spike/` и `phase2_backend/`. Это
изолированный **технический spike**, специально ограниченный двумя read-only
function tools. Он доказывает выбор runtime и зависимый tool calling, но не
является первым куском полного Scenario 1 backend.

Его fixture намеренно минимальна:

```text
initial input: device_id = POS-KZN17-03
model call 1:  get_device(POS-KZN17-03)
tool result:   attachment_id = ATT-KZN17-POS03-NIC
model call 2:  run_diagnostic(ATT-KZN17-POS03-NIC)
tool result:   LINK_DOWN observation
```

Initial input **не содержит** `attachment_id`. Приложение не вызывает tools
за модель и не переносит ID между вызовами. Acceptance проверяет, что второй
аргумент совпал с ID из фактического первого tool result, а не с зашитой
строкой.

Этот fixture не заменяет canonical Scenario 1 fixture ниже (`POS-KZN17-02`,
`INC-1042`, `ATT-KZN17-POS02`). Разные ID нужны, чтобы техническая проверка
runtime не стала незаметной подменой продуктового доменного контракта.

## Фаза 1 — local ADK/Gemini spike: завершена

В репозитории реализованы:

- native ADK `Runner` и `InMemorySessionService`;
- ровно два ordinary Python function tools: `get_device` и
  `run_diagnostic`;
- изоляция каждой попытки новой native ADK session;
- redacted audit-safe trace: сохраняются function calls/results, финальный
  ответ и ошибка, но не reasoning/thought fields;
- local tests, проверяющие границу двух tools, отсутствие attachment ID во
  входе и зависимость второго вызова от первого.

3 октября 2026 года выполнены три реальные независимые Gemini-попытки. Во
всех трёх модель вызвала ровно `get_device → run_diagnostic`; второй аргумент
был равен attachment ID из первого результата. Evidence:

- `traces/phase1-01-8ad59a3d.json`
- `traces/phase1-02-f6368a8b.json`
- `traces/phase1-03-95066547.json`
- `results/phase1-20261003T200708Z.json`

Эти generated files игнорируются Git, поскольку содержат transient results.
Полное delta-описание: `docs/handoff/ALP_ITSM_Agent_Handoff_v5.4_Phase_1_Update.md`.

### Наблюдение по ADK

ADK выдавал warning об experimental JSON-schema function declarations. Tools
работали; это не ошибка acceptance. Но после обновления ADK или model pin
обязателен повторный live regression spike: unit tests не доказывают поведение
модели.

## Фаза 2 — managed runtime spike: завершена в утверждённом scope

Цель Фазы 2 была узкой: проверить, что тот же минимальный Python/ADK/Gemini
runtime живёт вне локальной машины, получает ключ через managed secret и
делает ту же model-selected зависимую цепочку.

На Northflank создан временный публичный service `adk-spike`:

- runtime: `nf-compute-10`, shared 0.1 vCPU / 256 MB;
- образ: `python:3.12.14-slim`, service port 8080;
- endpoint `GET /health` сообщает только готовность и факт наличия ключа;
- endpoint `POST /spike/runs` запускает новый native ADK run и возвращает
  audit-safe observed calls/results;
- ключ хранится как Northflank secret, смонтированный в `/app/.env`; в Git,
  trace, report и документацию он не попадал.

Публичный verification URL: `https://p01--adk-spike--yxz5y8myjdln.code.run/`.
Это не production API: в нём нет auth, rate limiting, persistence, UI или
product observability.

4 октября 2026 года readiness и `/health` были passing, причём health
подтвердил наличие credential без раскрытия значения. Затем три независимых
внешних `POST /spike/runs` завершились со `status: completed` и
`validation.passed: true`. Каждый продемонстрировал:

```text
get_device(device_id="POS-KZN17-03")
  -> attachment_id="ATT-KZN17-POS03-NIC"
run_diagnostic(attachment_id="ATT-KZN17-POS03-NIC")
```

Внешний report сохранён как игнорируемый Git файл
`results/phase2-northflank-20261004T000427Z.json`.

### Исправленные проблемы совместимости

1. Первичная сборка упала из-за dependency conflict, а не Northflank:
   `fastapi==0.142.2` требовал `opentelemetry-api>=1.44`, тогда как ADK 2.10.0
   ограничивает его `<=1.42.1`. FastAPI закреплён на совместимой `0.141.1`;
   `pip check` чистый.
2. Первый managed secret file содержал bare value, а не dotenv assignment.
   В runner добавлен узкий loader: обычный dotenv или ровно одно bare secret
   value. Он не печатает и не сохраняет ключ.
3. После исправления локальная suite прошла `8 passed` (с одним неопасным
   FastAPI/Starlette deprecation warning); Northflank build и 3 external runs
   прошли.

### Что Фаза 2 доказала — и чего не доказала

Доказано: выбранная версия Python/ADK/model запускается в managed container;
Gemini доступен через secret; модель реально умеет пройти data dependency
между двумя tools вне локальной машины.

Не доказано: production reliability, cold-start SLA, безопасность публичного
API, PostgreSQL addon, persistent sessions, SSE reconnect, approval flow или
готовность Scenario 1. `3/3` — достаточный acceptance evidence для spike, не
статистическая гарантия. Database и Developer Sandbox-специфика исходного
большого плана остаются отдельной проверкой, когда появится продуктовый backend.

Полный delta: `docs/handoff/ALP_ITSM_Agent_Handoff_v5.5_Phase_2_Update.md`.

## Tool и domain contracts, зафиксированные после Фазы 2

Отдельный документ `docs/contracts/PHASE_2_TOOL_AND_DOMAIN_CONTRACTS.md`
фиксирует минимальную границу spike: schemas двух tools, result/error shapes,
read-only invariant, data dependency и rules validation. Это не «промпт для
LLM», а договор между всеми слоями:

- model-visible schema говорит модели, как вызвать tool;
- adapter/domain contract говорит коду, как валидировать вход и строить ответ;
- tests и acceptance проверяют, что обе стороны не расходятся;
- security boundary запрещает модели выбирать tenant/run context, читать
  секреты и выполнять mutation.

В Фазе 3 эти минимальные spike-contracts **уже расширены** отдельными
product-contracts CMDB, health, diagnostic, KB, evidence и proposal. Phase 2
документ остаётся историческим контрактом двух-tool runtime spike. Новый
mutation tool по-прежнему нельзя добавлять «по ходу» без отдельно
согласованных action/approval semantics.

## Canonical Scenario 1

### Fixture и initial event

Scenario 1 проверяет единичный недоступный платёжный терминал при здоровой
площадке:

| Поле | Значение |
| --- | --- |
| tenant | `TENANT-8OCT` |
| site | `SITE-KZN-017` |
| incident | `INC-1042` |
| affected terminal | `POS-KZN17-02` |
| peer terminal | `POS-KZN17-01` |
| CMDB attachment | `ATT-KZN17-POS02` |
| expected switch/port | `SW-KZN17-01 Gi1/0/18` |
| permitted diagnosis | `LOCAL_ACCESS_LINK_FAILURE` |
| hidden actual root cause | `PATCH_CABLE_DISCONNECTED` |

Initial `itsm.incident.created` event содержит incident, site, reported device
и симптомы, но не attachment, switch port, hidden root cause, expected answer,
evidence IDs и правильный tool sequence.

Агент должен установить, что site network и payment service healthy, peer
terminal reachable, а у affected terminal ожидаемый access port administratively
UP и operationally DOWN. Это поддерживает **local physical access-path fault**,
но не доказывает конкретно отключённый patch cable. Модель не вправе заявлять
точнее доступных evidence.

### Целевой набор Scenario 1 tools

| Tool | Назначение | Меняет мир? |
| --- | --- | --- |
| `get_device(device_id)` | CMDB topology и attachment | нет |
| `get_site_health(site_id)` | health площадки, сервиса и peer | нет |
| `run_diagnostic(diagnostic_type, target_id)` | проверка device/link по известному target | нет |
| `search_incidents(scope, entity_id)` | открытые тикеты/дубликаты | нет |
| `search_kb(query)` | ограниченный deterministic KB retrieval | нет |
| `propose_field_visit(...)` | создаёт лишь approval-required proposal | да, только proposal |

`search_incidents` и часть diagnostics не обязаны быть в фиксированной
последовательности. Success проверяется по валидному outcome и evidence, а не
по walkthrough. Полный продуктовый набор выше не должен задним числом
приписываться текущему двум-tool spike.

### Evidence contract

Каждый tool result возвращает structured data и immutable evidence record с
`evidence_id`, source type, captured time, entity IDs, tenant/run context и
typed payload. Свободный текст `facts` помогает UI/agent, но validator не
доверяет ему как источнику истины. Dynamic evidence подчиняется TTL.

Для `LOCAL_ACCESS_LINK_FAILURE` proposal validator требует evidence одного
run/tenant одновременно:

1. `CMDB_SNAPSHOT`: terminal → attachment → expected switch port;
2. `SITE_HEALTH`: площадка и payment service healthy, peer reachable,
   affected terminal unreachable;
3. `ACCESS_LINK_DIAGNOSTIC`: expected switch reachable, admin UP, operational
   DOWN, normal port security и expected configuration;
4. `KB_ARTICLE`: утверждённая текущая KB допускает onsite physical-path
   inspection для этого observation pattern.

Неточный, чужой, устаревший или неполный evidence set возвращает
`INSUFFICIENT_OR_INVALID_EVIDENCE`. Rationale LLM поясняет решение человеку,
но не является доказательством и не должен парситься validator-ом.

### Proposal и approval boundary

`propose_field_visit` создаёт immutable proposal, например с incident,
device, `LOCAL_ACCESS_LINK_FAILURE`, `ONSITE_FIELD_VISIT`, evidence IDs и
статусом `PENDING_APPROVAL`. Модель не выбирает очередь, адрес, инженера или
произвольный тип работ: domain layer детерминированно выводит разрешённые
параметры по action type и CMDB.

Human endpoint — обычный application endpoint, не tool модели. После proposal
ADK invocation может завершиться; ожидание решения сохраняется в Postgres,
а не удерживает зависший tool call.

При Approve domain layer в транзакции повторно валидирует актуальность:

- proposal всё ещё `PENDING_APPROVAL`;
- incident открыт и устройство всё ещё ему принадлежит;
- link всё ещё DOWN;
- отсутствуют существующий work order и equivalent executed action.

Если условие исчезло, decision сохраняется как APPROVED, proposal становится
`STALE`, но action не исполняется. Если валидно — создаются один `ExecutedAction`
и один `FieldServiceWorkOrder`, proposal становится `EXECUTED`, incident
`ESCALATED`, устройство остаётся `UNRESOLVED`. Повторный Approve возвращает
сохранённый result; idempotency исключает второй work order. Reject даёт
`REJECTED`, ноль executed actions и открытый incident.

После commit application outbox/input event передаёт фактический result в ту
же ADK session. Это не прямая запись во внутренние таблицы ADK и не внешняя
очередь.

### Scenario 1 success и hard failures

Успех означает валидный evidence-backed proposal, отсутствие execution до
approval, корректный approve/reject lifecycle и честный финальный текст:
onsite visit зарегистрирован, но device не объявляется восстановленным.

Hard failures включают proposal без обязательного evidence, cross-run/tenant
evidence, action до approval, дубликат после повторного approve, `RESOLVED`
после одного work order, точное утверждение о кабеле без доказательства,
fixture ground truth в prompt и test с единственным hard-coded tool sequence.

Минимальная agent instruction должна просить расследовать через available
tools, отличать observations от hypotheses, не фабриковать IDs/results и не
считать proposal execution. Она не должна подсказывать «сначала site health»,
ID KB, кабельную причину или нужную последовательность.

## Scenario 2 и 3: остаются в scope

**Scenario 2:** сигналы нескольких площадок, локальные сети healthy, общий
`payment_gateway_timeout`, provider `DEGRADED`. Агент сопоставляет evidence и
может предложить Major Incident; создание и массовое уведомление требуют
approval. Future offsets знает simulator, но не агент.

**Scenario 3:** VPN timeout при healthy Internet/DNS/gateway и истёкшем
сертификате пользователя. Исторический DNS case — лишь аналогия. Успех —
пересмотреть неподтверждённую гипотезу по evidence, а не заставить модель
совершить заранее заданную ошибку.

## Run lifecycle, события и UI (целевая реализация)

Сценарий стартует только по явному действию пользователя. Backend создаёт
`run_id`, копию mutable mock-world и ADK session. Fixture содержит относительные
offsets, но backend сохраняет фактические UTC timestamps; UI показывает
Europe/Moscow и фактическое смещение от старта.

Application владеет `Run`, `InputEvent`, `ActionProposal`, `Approval`,
`ExecutedAction` и activity log. Полезные UI events: `simulation.started`,
external signal, `tool.started`, `tool.finished`, `finding.recorded`,
`proposal.created`, `approval.decided`, `action.executed`, `run.status_changed`.
SSE будет передавать сохранённые events с последовательным номером и cursor,
без hidden reasoning.

В обычном состоянии ready backend должен принять start и сохранить
`simulation.started` без ожидания Gemini. Во время deploy/restart UI честно
показывает unavailable; «подготовка демо» не скрывает постоянный cold start.

## Риски и правила эксплуатации

- API key никогда не входит в Git. Локально он живёт в ignored `.env`; в
  Northflank — managed secret. Vercel не является хранилищем backend Gemini key.
- `results/` и `traces/` игнорируются; они не должны содержать secret или
  model reasoning.
- Временный Northflank endpoint публичен и годится только для acceptance
  spike. Перед демонстрацией продукта нужны auth, rate limits, observability
  и закрытие публичной testing surface.
- Каждое изменение ADK/model pin требует живого повторного запуска, потому
  что tool-use поведение — взаимодействие runtime и модели, не только Python
  unit test.
- Domain/tool errors уже typed и безопасны для model boundary; mapping в
  будущий product API ещё предстоит. Raw exception и secrets наружу не уходят.

## Фаза 3: Product contracts и domain foundation — PASS

Фаза 3 выполнена тремя внутренними checkpoint: 3A domain design/contracts,
3B deterministic business logic и 3C adapter/domain integration + regression.

Product code физически отделён от runtime spike в `product_backend/`.

### Что теперь есть в product domain

- pure domain entities/enums/errors/transitions;
- repository и source-system ports;
- ровно шесть Scenario 1 tool contracts:
  `get_device`, `get_site_health`, `run_diagnostic`,
  `search_incidents`, `search_kb`, `propose_field_visit`;
- trusted `ToolCallContext(tenant_id, run_id)` вне model-visible schema;
- immutable typed Evidence;
- deterministic proposal validator;
- human approval/execution service;
- stale и repeat-decision semantics;
- thin `DefaultScenario1ToolAdapter`, который делегирует application services
  и не имеет прямой зависимости от repositories/source-system ports;
- `Scenario1ReadToolService`, который оркестрирует repositories/providers и evidence creation;
- pure `domain/read_model.py`, где лежат type-aware ID ownership и topology/observation rules;
- explicit JSON-safe serialization boundary для typed tool results;
- CI gate для architecture/domain и полного repository regression.

Финальный technical contract:
`docs/contracts/PHASE_3_DOMAIN_AND_TOOL_CONTRACTS.md`.

### Evidence

Для `LOCAL_ACCESS_LINK_FAILURE + ONSITE_FIELD_VISIT` одновременно требуются:

1. CMDB terminal -> attachment -> expected switch/port;
2. healthy site/payment, reachable peer, unreachable affected terminal;
3. canonical access-link diagnostic: switch reachable, admin UP,
   operational DOWN, normal port security, expected configuration;
4. approved KB, разрешающая onsite physical-path inspection.

Validator читает typed payload, entity IDs, tenant/run ownership и TTL; LLM
`facts`/rationale не являются evidence.

Dynamic `SITE_HEALTH` и `ACCESS_LINK_DIAGNOSTIC` evidence имеют обязательный
положительный TTL. Конкретная длительность задаётся application configuration,
а не моделью и не зашита в domain contract. Validator дополнительно отвергает
future/naive/non-comparable timestamps, expiry <= captured_at и уже истёкшие
records.

### Tool boundary, ownership и data dependency

Model-facing adapter остаётся тонким. Ownership и provider orchestration
выполняет application/domain path.

Device и site проверяются **по типу сущности**: наличие строки в чужом evidence
само по себе не делает её разрешённым device/site ID. Поэтому, например, KB
article ID или найденный incident ID нельзя использовать как device.

Diagnostic можно запустить только по attachment, ранее полученному из
`CMDB_SNAPSHOT`. Если для attachment есть несколько snapshots, используется
самый новый известный. Provider result до записи evidence cross-check-ится с
canonical topology: device/site, attachment, switch и port не могут тихо
подмениться; неполный CMDB topology также не становится evidence.

Product `run_diagnostic` сохраняет Phase 2 обязательные top-level output fields
`attachment_id`, `diagnostic`, `observed_state`; canonical down observation
по-прежнему сериализуется как `LINK_DOWN`.

Таким образом исходный принцип data dependency переносится из two-tool spike
в настоящий Scenario 1, но без жёстко заданной последовательности всех tools.
Regression содержит отдельный success-case с другим допустимым порядком
read-tools.

### Proposal / approval

`propose_field_visit` создаёт только `PENDING_APPROVAL` proposal.

Approve/Reject не являются model tools. При Approve application/domain layer
делает fresh CMDB + access-link revalidation и проверяет pending proposal,
OPEN incident/device ownership и отсутствие existing work order/equivalent
executed action.

Если authoritative условие исчезло, decision сохраняется APPROVED, proposal
становится `STALE`, execution = 0. Если provider временно недоступен,
approval не потребляется: proposal остаётся pending, возвращается safe
retryable typed error.

Валидный Approve создаёт ровно один `ExecutedAction` и один
`FieldServiceWorkOrder`, proposal -> `EXECUTED`, incident -> `ESCALATED`.
Work-order topology fields выводятся из trusted current CMDB. Сам work order не
является repair evidence и не переводит incident в `RESOLVED`.

Повтор того же human decision возвращает stored result. Защита от реально
конкурентных HTTP requests должна дополнительно обеспечиваться transaction +
unique constraints в будущей PostgreSQL implementation; эти invariants уже
зафиксированы repository contracts.

### Error semantics

Model/UI-facing ошибки typed и не содержат raw provider exception/secrets.

Для approval revalidation различается:

- authoritative `None`/absence -> состояние действительно исчезло, proposal
  может стать `STALE`;
- provider exception/outage -> retryable typed error, human approval не
  потребляется.

### Проверки Фазы 3

После отдельного финального аудита 3A+3B+3C GitHub Actions
`Phase 3 domain check`:

- architecture/domain gate: **69 passed**;
- pinned `requirements.txt`: `pip check` — no broken requirements;
- полный Python regression: **77 passed, 1 dependency deprecation warning**;
- retained Node spike tests: **5 passed, 0 failed**.

Architecture tests отдельно запрещают framework/application/ports dependencies
в pure domain, direct repository/source-port access из model-facing adapter и
canonical fixture/hidden root-cause constants в `product_backend/`. Typed
tool results проверяются на JSON-safe serialization.

Warning относится к FastAPI/Starlette TestClient dependency surface.

Live Gemini в Фазе 3 повторно не запускался: ADK/model pin и Phase 1/2 runtime
agent не менялись, а live six-tool ADK wiring ещё не входит в эту фазу.

## Следующий шаг: Фаза 4 — Persistent application backend foundation

После закрытой Фазы 3 следующий этап фиксируется как **Фаза 4**.

Её цель — превратить headless domain foundation в устойчивый stateful
application backend, но **не** пытаться одновременно построить UI и live
six-tool agent.

Фаза 4 детализирует уже зафиксированный после Phase 3 порядок и не меняет
domain contracts.

### Scope Фазы 4

#### 4A. PostgreSQL persistence

1. выбрать/подключить PostgreSQL для product backend;
2. создать migrations/schema для product-owned state, минимум:
   - runs;
   - incidents;
   - evidence;
   - action proposals;
   - approvals;
   - executed actions;
   - field-service work orders;
   - persisted application events/outbox;
3. реализовать concrete repositories/UoW по ports Фазы 3;
4. обеспечить transactionality и database uniqueness для approval/action/work
   order invariants;
5. доказать tenant_id/run_id isolation и восстановление состояния после restart.

Точный managed PostgreSQL provider handoff не фиксирует заранее: это
implementation decision Фазы 4. PostgreSQL как тип persistent store уже
зафиксирован архитектурой.

#### 4B. Persisted application lifecycle и audit

1. добавить persistent application event/audit model;
2. каждый внешний event, tool observation/result, proposal, approval и
   executed action связывать с run_id;
3. event sequence должен быть монотонным внутри одного run и пригодным для
   будущего SSE cursor/reconnect;
4. server-side timestamps authoritative; fixture хранит относительные offsets,
   а backend — фактические UTC timestamps;
5. не сохранять hidden chain-of-thought/model reasoning;
6. сохранить возможность реконструировать operational timeline только из
   persisted safe records.

Минимальные event types остаются из target design:

- simulation.started;
- external signal;
- tool.started;
- tool.finished;
- finding.recorded;
- proposal.created;
- approval.decided;
- action.executed;
- run.status_changed.

#### 4C. Product FastAPI application boundary

Добавить минимальные product endpoints поверх persistence/application layer:

- explicit Scenario 1 run start;
- чтение current run/state;
- human Approve;
- human Reject;
- необходимые read endpoints для следующего UI/SSE слоя.

Ready backend должен уметь принять start, создать run и сохранить
`simulation.started` **без ожидания Gemini**.

Human endpoints вызывают уже существующий deterministic approval/execution
boundary; API не дублирует domain rules.

### Acceptance Фазы 4

Фаза 4 считается PASS только если:

1. product state больше не зависит от process memory;
2. restart backend не уничтожает созданные runs/evidence/proposals/approvals;
3. repositories реально реализуют ports Фазы 3;
4. повторный Approve после commit не создаёт второй action/work order;
5. concurrent duplicate protection подтверждается database transaction/unique
   constraints, а не только последовательным unit-test;
6. cross-tenant/cross-run reads и writes блокируются;
7. persisted events имеют монотонный per-run seq и server timestamp;
8. API errors остаются typed/safe и не раскрывают raw exception/secrets;
9. полный regression Фаз 1–3 остаётся зелёным;
10. Phase 4 получает собственные persistence/API integration tests.

### Что НЕ входит в Фазу 4

Не добавлять в этот этап:

- Next.js operational console;
- визуальную полировку;
- фактический SSE endpoint/клиент;
- live wiring шести product tools в Google ADK;
- Scenario 2/3;
- новые mutation tools;
- изменение domain semantics Фазы 3 без найденной технической причины.

Это сознательное разбиение: сначала persistent backend и audit trail, затем
delivery/UI и только потом полный live agent vertical slice.

### После Фазы 4

Предварительный порядок, который следует уточнить после PASS Фазы 4:

- **Фаза 5:** persisted SSE + operational UI;
- **Фаза 6:** live six-tool Google ADK wiring + полный Scenario 1 E2E
  acceptance;
- затем Scenario 2, Scenario 3 и финальный polish/deploy.

Эти номера после Phase 4 пока являются roadmap, а не implementation contract.

## Быстрая проверка repository

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m phase1_adk_spike.runner --runs 3
```

Для live Phase 1/2 run нужен `GOOGLE_API_KEY` в ignored local `.env`; без него
runner останавливается до network request и записывает безопасный `not_run`
report. Docker/Northflank path использует тот же pinned requirements и secret
только в runtime environment.

Для Phase 3 regression отдельный CI workflow выполняет compileall, domain tests
и полный `pytest -q`/Node regression без live Gemini request.



## Передача в новый этап

Для нового чата/агента использовать именно этот cumulative handoff v5.7 как
основную точку входа вместе с repository branch, содержащей закрытую Фазу 3.

Стартовая инструкция следующему исполнителю:

> Фазы 0–3 закрыты. Не пересматривать Scenario 1/domain contracts без
> технически доказанной причины. Начать Фазу 4 с ревью текущих repository/UoW
> ports и проектирования PostgreSQL persistence. Не начинать UI, SSE или live
> six-tool ADK wiring до PASS persistent application backend.

После завершения Фазы 4 снова выпустить два документа: Phase 4 delta update и
новый cumulative handoff.
