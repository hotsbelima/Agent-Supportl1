# Phase 4A — PostgreSQL persistence implementation checkpoint

Дата: 4 октября 2026 года.  
Статус: **IMPLEMENTED, NOT YET VERIFIED**.

Этот документ фиксирует implementation checkpoint 4A поверх закрытой Фазы 3.
Он не объявляет Phase 4 PASS и не заменяет cumulative handoff v5.7.

По явной инструкции на этом проходе **тесты не добавлялись и не запускались**.
PostgreSQL integration/concurrency/restart acceptance остаётся отдельной
проверкой перед закрытием Phase 4.

## 1. Граница checkpoint

Реализован только scope 4A из cumulative handoff:

- PostgreSQL schema/migration для product-owned state;
- concrete SQLAlchemy repositories по ports Фазы 3;
- concrete transactional Units of Work;
- DB-level uniqueness для proposal/approval/execution/work-order invariants;
- tenant/run composite keys и foreign-key boundaries;
- persistence mapping immutable typed Evidence в PostgreSQL JSONB;
- storage foundation для будущих persisted application events/outbox.

Не реализованы и не должны считаться частью этого checkpoint:

- application event/audit lifecycle 4B;
- event sequence allocator;
- FastAPI product routes 4C;
- SSE;
- UI;
- live six-tool ADK wiring;
- Scenario 2/3;
- новые domain semantics.

## 2. Технологический выбор

Persistence stack:

- PostgreSQL;
- SQLAlchemy 2.0 async API;
- psycopg 3 async driver;
- Alembic migrations.

Deployment получает connection string только через `DATABASE_URL`.
`normalize_database_url()` принимает common managed forms
`postgres://...` / `postgresql://...` и преобразует их в
`postgresql+psycopg://...`. Credential не логируется и не попадает в
domain/application state.

## 3. Schema

Initial migration:
`alembic/versions/20261004_0001_phase4a_product_state.py`.

Создаются таблицы:

1. `runs`
2. `incidents`
3. `evidence`
4. `action_proposals`
5. `approvals`
6. `executed_actions`
7. `field_service_work_orders`
8. `application_events`
9. `application_outbox`

Все Scenario 1 mutable/product-owned child records несут `tenant_id` и
`run_id`. Composite foreign keys не позволяют silently привязать proposal,
approval, action или work order к сущности другого tenant/run.

### Evidence storage

Evidence остаётся domain entity Фазы 3. В БД:

- `source_type` хранит canonical enum value;
- `entity_ids` и `facts` — PostgreSQL arrays;
- typed payload — JSONB;
- `captured_at` / `expires_at` — timezone-aware timestamps.

`persistence/serialization.py` содержит explicit mapping каждого из пяти
Phase 3 payload types. Generic dataclass dump не используется: source type и
payload class должны совпадать.

## 4. Repository implementation

`product_backend/persistence/repositories.py` реализует существующие ports:

- RunRepository
- IncidentRepository
- EvidenceRepository
- ProposalRepository
- ApprovalRepository
- ExecutedActionRepository
- WorkOrderRepository

Query methods всегда фильтруют по `tenant_id + run_id` перед entity ID.
Таким образом одинаковый business ID в другом run/tenant не становится
доступным через текущий context.

Domain models не импортируют SQLAlchemy и не знают о PostgreSQL.

## 5. Transaction boundaries

`product_backend/persistence/uow.py` реализует три UoW Фазы 3:

- `SqlAlchemyToolReadUnitOfWork`
- `SqlAlchemyProposalCreationUnitOfWork`
- `SqlAlchemyApprovalExecutionUnitOfWork`

Каждый UoW создаёт отдельную AsyncSession и одну transaction. Если application
service выходит без explicit commit либо бросает exception, UoW делает
rollback и закрывает session.

### Proposal serialization

Proposal creation блокирует current run row `FOR UPDATE`. Concurrent creation
для одного run после ожидания обязана заново увидеть актуальный run state.
Partial unique index дополнительно запрещает больше одного
`PENDING_APPROVAL` proposal на incident внутри tenant/run.

### Approval serialization

Approval path первым чтением proposal использует `SELECT ... FOR UPDATE`.
Поэтому два конкурентных решения для одного proposal не должны оба пройти
check-before-write одновременно: второй transaction ждёт первый commit и
после него может увидеть уже сохранённый Approval.

Это дополняется независимыми DB constraints:

- максимум один Approval на proposal;
- максимум один ExecutedAction на proposal;
- максимум один equivalent ExecutedAction для
  tenant/run/incident/device/action_type;
- максимум один FieldServiceWorkOrder на proposal;
- максимум один Scenario 1 FieldServiceWorkOrder на incident.

Row locking даёт корректный transactional path; unique constraints остаются
последней защитой данных.

## 6. Events/outbox boundary

4A создаёт только persistence schema:

`application_events`
- primary key: tenant/run/seq;
- unique tenant/run/event_id;
- event type, server timestamp slot и JSONB payload.

`application_outbox`
- tenant/run ownership;
- topic/payload;
- created/available/delivered timestamps;
- attempt counter.

Запись событий, authoritative timestamping, monotonic sequence allocation,
timeline reconstruction и delivery semantics относятся к **4B** и сейчас
намеренно не реализованы.

## 7. Alembic usage

Migration требует explicit environment variable и не содержит fallback
credential:

```powershell
$env:DATABASE_URL = "postgresql://<user>:<password>@<host>:<port>/<db>"
alembic upgrade head
```

Managed provider выбирается отдельно при infrastructure acceptance. Handoff
фиксирует PostgreSQL как store, но не конкретного vendor.

## 8. Что ещё НЕ доказано

На этом checkpoint не доказаны:

- что migration реально применяется к PostgreSQL;
- repository round-trip для всех entities;
- restart persistence;
- cross-tenant/cross-run integration behavior;
- два реальных concurrent Approve;
- compatibility нового dependency set через `pip check`;
- regression Фаз 1–3.

Эти пункты нельзя считать PASS по наличию кода. Они должны быть проверены
отдельно. Финальный infrastructure acceptance на реальном PostgreSQL/Northflank
позже выполняется отдельно, как уже согласовано.

## 9. Files

Новый persistence layer:

- `product_backend/persistence/database.py`
- `product_backend/persistence/tables.py`
- `product_backend/persistence/serialization.py`
- `product_backend/persistence/repositories.py`
- `product_backend/persistence/uow.py`
- `product_backend/persistence/__init__.py`

Migration surface:

- `alembic.ini`
- `alembic/env.py`
- `alembic/script.py.mako`
- `alembic/versions/20261004_0001_phase4a_product_state.py`

Dependencies are pinned in `requirements.txt`.

## 10. Verification status

**No tests were written or executed in this implementation pass.**

Следующий шаг после review — отдельный Phase 4A verification pass:
persistence integration tests + PostgreSQL migration/round-trip/isolation/
concurrency checks. До этого 4A является implemented checkpoint, но не
verified PASS.
