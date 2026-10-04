# Phase 4A — PostgreSQL persistence implementation checkpoint

Дата: 4 октября 2026 года.  
Статус: **IMPLEMENTED + POSTGRESQL CI VERIFIED; MANAGED-INFRA ACCEPTANCE PENDING**.

Этот документ фиксирует implementation checkpoint 4A поверх закрытой Фазы 3.
Он не объявляет Phase 4 PASS и не заменяет cumulative handoff v5.7.

Первый implementation pass был намеренно выполнен без тестов. После отдельного
логического аудита добавлена PostgreSQL integration suite и выполнен полный CI
на реальном PostgreSQL 16 service container. Managed Northflank deployment/
restart acceptance остаётся отдельной проверкой перед закрытием Phase 4.

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

## 8. Что доказано PostgreSQL CI

GitHub Actions workflow `Phase 4A PostgreSQL persistence check` прошёл на
Python 3.12.14 + PostgreSQL 16:

- pinned dependencies installed; `pip check`: no broken requirements;
- compileall: PASS;
- Alembic `upgrade head`: PASS;
- `alembic check`: no new upgrade operations detected;
- `downgrade base -> upgrade head`: PASS;
- Phase 3 architecture/domain regression: **69 passed**;
- Phase 4A PostgreSQL integration suite: **7 passed**;
- full Python regression: **84 passed, 1 existing dependency warning**;
- retained Node regression: **5 passed, 0 failed**.

Phase 4A integration suite проверяет:

- PostgreSQL-only URL boundary;
- strict typed Evidence JSONB serialization/deserialization;
- наличие всех девяти product-owned tables;
- repository round-trip всех пяти typed Evidence payload classes;
- сохранение state после dispose/recreate database engine;
- tenant/run read isolation;
- composite-FK rejection cross-tenant child write;
- два реальных concurrent Approve через разные DB transactions;
- ровно один Approval, ExecutedAction и FieldServiceWorkOrder;
- replay повторного Approve без duplicate side effects.

Первый CI attempt остановился на compileall из-за буквальных `\\n`, случайно
попавших в одну строку ORM mapping при GitHub patch. Файл исправлен; итоговый
полный run после исправления зелёный.

### Что ещё не является managed-infrastructure proof

Этот CI использует настоящий PostgreSQL, но ephemeral GitHub service container,
а не Northflank managed database/backend. Поэтому окончательный Phase 4
infrastructure acceptance всё ещё должен подтвердить deployment, secrets,
migration и state survival после реального backend restart/redeploy на
Northflank. Это не подменяется CI.

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

**Phase 4A implementation and PostgreSQL CI verification: PASS.**

Это не означает полный Phase 4 PASS: 4B/4C ещё не реализованы, а managed
Northflank infrastructure acceptance выполняется отдельно перед закрытием
Phase 4.
