# Phase 4B — Persisted application lifecycle and audit

Дата: 4 октября 2026 года.  
Статус: **PASS (PostgreSQL CI verified)**.

Этот checkpoint продолжает verified Phase 4A persistence foundation и
реализует только scope 4B из cumulative handoff v5.7. Product FastAPI boundary
4C, SSE, UI и live six-tool ADK wiring сюда не входят.

## 1. Что реализовано

Добавлен persistent application lifecycle/audit layer:

- закрытый contract application event types;
- безопасный JSON payload boundary;
- PostgreSQL event repository;
- монотонный per-run `seq`;
- server-side UTC `occurred_at`;
- transactional outbox row на каждый persisted event;
- timeline read с `after_seq` cursor;
- application lifecycle service;
- audit wiring для tool calls, proposals, approvals, actions и run-state changes;
- PostgreSQL migration с lifecycle integrity constraints.

Поддерживаются зафиксированные handoff event types:

- `simulation.started`
- `external.signal`
- `tool.started`
- `tool.finished`
- `finding.recorded`
- `proposal.created`
- `approval.decided`
- `action.executed`
- `run.status_changed`

## 2. Event contract и safe payload

Контракт находится в `product_backend/contracts/events.py`.

Каждый `ApplicationEvent` содержит:

- `event_id`
- `tenant_id`
- `run_id`
- `seq`
- `event_type`
- `occurred_at`
- JSON-safe `payload`

Payload validator принимает только JSON primitives/arrays/objects, отвергает
non-finite numbers и запрещает persistence ключей, относящихся к hidden model
reasoning или credential material, включая:

- `thought` / `thoughts`
- `reasoning`
- `chain_of_thought`
- `model_reasoning`
- `internal_reasoning`
- `hidden_reasoning`
- API keys/password/secrets/access/refresh tokens.

Публичный proposal rationale и finding summary разрешены: это observable
application data, а не hidden chain-of-thought.

## 3. Monotonic sequence

`SqlAlchemyApplicationEventRepository.append()` перед выделением sequence
делает `SELECT ... FOR UPDATE` owning run row.

После lock читается текущий `MAX(application_events.seq)` только внутри
данного `tenant_id/run_id`, следующий event получает `max + 1`.

Следствия:

- writers одного run сериализуются;
- разные runs не используют глобальный counter и не блокируют друг друга;
- DB primary key `tenant_id/run_id/seq` остаётся последней защитой;
- `seq` дополнительно имеет CHECK `seq > 0`.

Это делает persisted events пригодными для будущего SSE cursor/reconnect без
реализации самого SSE в Phase 4B.

## 4. Server-side time

Caller не передаёт `occurred_at` в event repository.

Repository получает timestamp от trusted backend clock и приводит его к UTC.
Naive timestamp отвергается.

Fixture relative offsets могут находиться внутри explicit event details как
scenario data, но не управляют authoritative event timestamp.

## 5. Transactional outbox

Каждый persisted event создаёт ровно один `application_outbox` row в той же
DB transaction.

4B migration добавляет:

- FK `tenant_id/run_id/event_seq -> application_events`;
- UNIQUE `tenant_id/run_id/event_seq`.

Outbox payload содержит safe event envelope:

- event ID;
- event type;
- sequence;
- UTC occurrence timestamp;
- safe event payload.

Actual outbox delivery/consumer semantics не запускаются в 4B. Storage готов
для последующего application delivery/ADK feedback/SSE layers.

## 6. Tool lifecycle

`DefaultScenario1ToolAdapter` теперь может получать
`ApplicationLifecycleService`.

При product composition с lifecycle service:

1. `tool.started` коммитится короткой transaction до application operation;
2. successful read-tool result создаёт `tool.finished` в одной transaction с
   соответствующим Evidence;
3. successful `propose_field_visit` создаёт `tool.finished` в одной
   transaction с proposal/run-state mutation;
4. unsuccessful tool result получает persisted `tool.finished` с безопасным
   typed error result;
5. unexpected exception не раскрывается наружу и также нормализуется.

Model-visible schemas шести tools не изменились.

Phase 3 in-memory test composition остаётся допустима без lifecycle service;
production PostgreSQL composition использует lifecycle service + event-enabled
UoWs.

## 7. Business lifecycle events

### Proposal

Успешный field-visit proposal transaction сохраняет:

- ActionProposal;
- run -> `WAITING_APPROVAL`;
- `proposal.created`;
- `run.status_changed`;
- successful `tool.finished`.

### Human decision

Reject transaction сохраняет:

- Approval;
- proposal -> `REJECTED`;
- run -> `ACTIVE`;
- `approval.decided`;
- `run.status_changed`.

Approve со stale condition сохраняет:

- APPROVED decision;
- proposal -> `STALE`;
- zero execution;
- `approval.decided`;
- `run.status_changed`.

Valid Approve transaction сохраняет:

- Approval;
- ExecutedAction;
- FieldServiceWorkOrder;
- proposal -> `EXECUTED`;
- incident -> `ESCALATED`;
- run -> `ACTIVE`;
- `approval.decided`;
- `action.executed`;
- `run.status_changed`.

Replay уже сохранённого human decision не создаёт новых lifecycle events.

## 8. Generic lifecycle service

`ApplicationLifecycleService` предоставляет application boundary для:

- `record_simulation_started`;
- `record_external_signal`;
- `record_tool_started`;
- `record_tool_finished`;
- `record_finding`;
- `timeline(after_seq, limit)`.

`simulation.started` проверяет соответствие `scenario_id` owning Run.

`finding.recorded` требует Evidence IDs текущего tenant/run; foreign/missing
evidence не может попасть в timeline.

Timeline читается исключительно из persisted `application_events` и всегда
возвращается по возрастанию `seq`.

## 9. Database migration

Phase 4B migration:

`alembic/versions/20261004_0002_phase4b_lifecycle_integrity.py`

Она накладывается поверх Phase 4A `20261004_0001`.

CI проверяет полный:

`upgrade 0001 -> 0002 -> downgrade base -> upgrade head`

и затем `alembic check`.

## 10. PostgreSQL verification

Финальный полный workflow:

`Phase 4B persisted lifecycle check`

GitHub Actions run: `37226065005`.

Environment:

- Python 3.12.14;
- PostgreSQL 16;
- pinned project dependencies.

Результаты:

- `pip check`: no broken requirements;
- compileall: PASS;
- migrations upgrade/check/downgrade/re-upgrade: PASS;
- Phase 3 architecture/domain regression: **69 passed**;
- Phase 4A PostgreSQL regression: **7 passed**;
- Phase 4B lifecycle suite: **5 passed**;
- full Python regression: **89 passed, 1 existing dependency warning**;
- retained Node regression: **5 passed, 0 failed**.

4B suite доказывает:

- hidden reasoning/credential keys блокируются;
- 12 concurrent writers одного run получают contiguous `seq 1..12`;
- каждый event получает ровно один outbox row;
- server UTC timestamp authoritative;
- cursor `after_seq` работает;
- cross-run/foreign finding evidence блокируется;
- successful и failed tool calls имеют persisted start/finish;
- proposal -> approval -> action timeline полный;
- approval replay не создаёт повторных events/outbox records.

Первый CI run после реализации остановился на Phase 3 architecture assertion:
test жёстко ожидал у thin adapter только два application-service dependency.
Phase 4B добавил третий application dependency
`lifecycle_service`. Сам architecture invariant не изменился: adapter всё
ещё не зависит напрямую от repositories/source-system ports. Assertion был
обновлён на новый разрешённый application boundary, после чего полный pipeline
прошёл.

## 11. Что не входит в 4B

Не реализованы:

- FastAPI product endpoints;
- explicit Scenario 1 HTTP start;
- human Approve/Reject HTTP routes;
- API error mapping;
- фактический SSE endpoint;
- Next.js UI;
- live six-tool Google ADK wiring;
- Scenario 2/3.

Это scope 4C и последующих фаз.

## 12. Текущий статус Phase 4

- 4A PostgreSQL persistence: **PASS in PostgreSQL CI**;
- 4B persisted lifecycle/audit: **PASS in PostgreSQL CI**;
- 4C Product FastAPI boundary: **NEXT**;
- managed Northflank deployment/restart acceptance: pending final Phase 4
  infrastructure pass.

Полный Phase 4 PASS пока не объявляется.
