# Phase 9A — UI terminology

The public demo UI is Russian. Canonical domain/entity names remain English in
code, API contracts, persistence schemas, tests where they refer to wire-level
values, and this glossary.

| Russian UI label | Canonical English entity / term |
| --- | --- |
| Запуск | Run |
| Инцидент | Incident |
| Сервисный инцидент | Service Incident |
| Наблюдение | Evidence / Observation |
| Предложение | Proposal |
| Решение человека | Human approval / rejection (HITL) |
| Выполненное действие | Executed Action |
| Заявка на выезд | Field Service Work Order |
| Выездной сервис | Field Service |
| Операционный сигнал | Operational Signal |
| Крупный инцидент | Major Incident |
| Предложение крупного инцидента | Major Incident Proposal |
| Выполнение крупного инцидента | Major Incident Execution |
| Хронология / журнал аудита | Persisted Application Event Timeline |
| Состояние продукта | Product state / Product business truth |
| Поток событий | persisted SSE |
| Перепланирование | evidence-driven replanning |

## Rule

Do not rename wire-level enum values, JSON fields, database columns, event
types, tool names, or API paths merely to localize the UI. Localization belongs
to the presentation layer. Hidden chain-of-thought is never exposed or
translated because it is not Product state.
