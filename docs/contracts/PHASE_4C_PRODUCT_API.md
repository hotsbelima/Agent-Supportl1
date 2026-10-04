# Phase 4C — Product FastAPI application boundary

Дата: 4 октября 2026 года.  
Статус: **IMPLEMENTED / NOT TESTED**.

Этот checkpoint реализует только 4C поверх verified Phase 4A/4B. По явной
инструкции на этом проходе тесты для 4C **не добавлялись и не запускались**.
Полный Phase 4 PASS пока не объявляется.

## 1. Scope

Реализован минимальный persistent product HTTP boundary:

- explicit Scenario 1 run start;
- current run/state read;
- persisted timeline read для будущего UI/SSE;
- human Approve;
- human Reject;
- safe typed HTTP errors;
- runtime composition PostgreSQL + application services;
- health endpoint с реальной проверкой PostgreSQL reachability.

Не реализованы:

- SSE endpoint;
- Next.js UI;
- live Google ADK six-tool wiring;
- Scenario 2/3;
- новые mutation tools;
- authentication/authorization system;
- managed Northflank acceptance.

## 2. Product API package

Новый composition package:

- `product_api/app.py`
- `product_api/schemas.py`
- `product_api/scenario1_fixture.py`
- `product_api/__main__.py`

Запуск:

```bash
python -m product_api
```

или:

```bash
uvicorn product_api.app:app --host 0.0.0.0 --port 8000
```

Runtime получает PostgreSQL connection только через `DATABASE_URL`.

## 3. Tenant context

Все product state endpoints требуют header:

`X-Tenant-ID`

Допустимый формат ограничен безопасным identifier pattern и длиной 128.

Это **не auth**. Header является trusted demo/application context. До
публичного production-like demo реальная identity должна быть связана с tenant
на authentication/authorization boundary.

Все persistence reads/writes после API boundary по-прежнему используют
`tenant_id + run_id`; header не заменяет database isolation из Phase 4A.

## 4. Scenario 1 start

Endpoint:

`POST /api/v1/scenario-1/runs`

Start не вызывает Gemini и не создаёт ADK session.

Одна PostgreSQL transaction:

1. создаёт `Run` в `CREATED`;
2. создаёт initial Incident;
3. сохраняет `simulation.started`;
4. сохраняет initial external event `itsm.incident.created`;
5. применяет существующий domain transition `CREATED -> ACTIVE`;
6. сохраняет `run.status_changed`;
7. commit.

После commit endpoint читает persisted state обратно и возвращает
`RunStateResponse`.

Таким образом ready backend может создать run и persisted
`simulation.started` независимо от Gemini/ADK.

## 5. Scenario fixture placement

Canonical Scenario 1 bootstrap/approval-source IDs находятся в
`product_api/scenario1_fixture.py`, а не в `product_backend`.

Fixture содержит только observable Scenario 1 data, нужные API composition и
approval revalidation:

- `INC-1042`
- `SITE-KZN-017`
- `POS-KZN17-02`
- peer terminal;
- attachment;
- switch/port;
- deterministic current monitoring observation.

Hidden actual root cause в API fixture не добавлен.

Это сохраняет Phase 3 architecture rule: reusable domain/application package
не содержит canonical fixture/hidden-answer constants.

## 6. Current state read

Endpoint:

`GET /api/v1/runs/{run_id}`

Возвращает tenant/run-scoped persisted snapshot:

- Run;
- Incidents;
- Evidence;
- ActionProposals;
- Approvals;
- ExecutedActions;
- FieldServiceWorkOrders;
- `latest_event_seq`.

API не собирает state из process memory.

Persistence read implementation находится в
`product_backend/persistence/run_state.py`.

## 7. Timeline read

Endpoint:

`GET /api/v1/runs/{run_id}/events?after_seq=<cursor>&limit=<n>`

Возвращает уже persisted safe events из Phase 4B, ordered по `seq`, и
`next_cursor`.

Это read endpoint для следующего UI/SSE слоя. Фактический SSE transport в 4C
не реализуется.

Limits:

- `after_seq >= 0`;
- `1 <= limit <= 1000`.

## 8. Human Approve / Reject

Endpoints:

- `POST /api/v1/runs/{run_id}/proposals/{proposal_id}/approve`
- `POST /api/v1/runs/{run_id}/proposals/{proposal_id}/reject`

Body:

```json
{
  "decided_by": "human-operator"
}
```

HTTP layer **не реализует approval business rules**.

Оба endpoint делегируют существующему
`FieldVisitApprovalService.decide(...)`:

- Approve -> `ApprovalDecision.APPROVED`;
- Reject -> `ApprovalDecision.REJECTED`.

Поэтому Phase 3/4A semantics сохраняются:

- fresh revalidation;
- stale semantics;
- repeat-decision replay;
- database duplicate protection;
- exactly-one action/work-order invariant;
- no RESOLVED from work-order creation.

Для approval revalidation API composition использует deterministic Scenario 1
CMDB/monitoring sources из `product_api/scenario1_fixture.py`.

## 9. HTTP schemas

`product_api/schemas.py` содержит explicit response/input models:

- `RunStateResponse`;
- `TimelineResponse`;
- `ApprovalDecisionResponse`;
- `HumanDecisionRequest`;
- `ApiErrorResponse`.

Operational state views не содержат hidden model reasoning.

Evidence payload остаётся typed domain data, сериализованный в JSON-safe
object.

## 10. Safe error boundary

Domain errors map в stable HTTP classes:

- not-found/context -> 404;
- invalid state/proposal/evidence conflict -> 409;
- upstream dependency unavailable -> 503;
- remaining invalid arguments -> 400.

FastAPI request validation возвращает generic typed 422 без echo raw input.

SQLAlchemy failures возвращают:

- HTTP 503;
- code `DATABASE_UNAVAILABLE`;
- generic retryable message.

Unexpected exceptions возвращают generic typed 500:

- code `INTERNAL_ERROR`;
- без `repr(exception)`;
- без stack trace;
- без provider payload;
- без secret/connection string.

## 11. Health

Endpoint:

`GET /health`

Health выполняет реальный `SELECT 1` через configured async PostgreSQL engine.
Если database недоступна, SQLAlchemy error handler отдаёт safe 503.

Successful health сообщает:

- Phase 4 / checkpoint 4C;
- database configured/reachable;
- `adk_wired=false`;
- `sse_wired=false`.

То есть endpoint не притворяется, что будущие Phase 5/6 capabilities уже
существуют.

## 12. Application additions

В `product_backend` добавлены generic, fixture-independent components:

- `Scenario1Bootstrap`;
- `Scenario1RunStarted`;
- `RunStateSnapshot`;
- `Scenario1RunStartService`;
- `RunStateService`;
- `RunStateQueryPort`;
- `SqlAlchemyRunStateQuery`;
- `SqlAlchemyRunStartUnitOfWork`.

Domain entities, validators, Scenario 1 diagnosis/action semantics и approval
rules не изменены.

## 13. Verification status

**4C пока не тестировалась.**

По явной инструкции в этом implementation pass:

- не создавался `tests/test_phase4c_*.py`;
- не запускался pytest;
- не запускался compileall;
- не запускался GitHub Actions verification;
- не выполнялся реальный HTTP/PostgreSQL smoke;
- не выполнялся Northflank deploy/restart acceptance.

Выполнен только ручной логический review кода и границ scope.

Поэтому текущий статус:

- Phase 4A: PostgreSQL CI verified;
- Phase 4B: PostgreSQL CI verified;
- Phase 4C: **IMPLEMENTED / NOT TESTED**;
- Phase 4 overall: **NOT PASS YET**.

Следующий шаг после отдельной команды — verification 4C/полный Phase 4 local-CI
pass, затем согласованный managed Northflank infrastructure acceptance.
