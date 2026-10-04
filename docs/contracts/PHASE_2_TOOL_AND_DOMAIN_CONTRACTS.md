# Фаза 2 — contracts tools и предметной области

Дата фиксации: 4 октября 2026 года. Этот документ зафиксирован после успешной
внешней проверки runtime и является основанием для следующего шага Scenario 1.
Он не добавляет БД, UI, approvals или workflow-движок.

## Зачем это нужно

Contract — это точная договорённость на границе компонентов. В данном случае
она одновременно задаёт:

- что LLM может попросить у инструмента;
- что инструмент обязан вернуть и какие данные может использовать следующий
  инструмент;
- какие сущности существуют в предметной области и какие их состояния
  допустимы;
- как отличить нормальный ответ от ошибки, не заставляя модель угадывать
  формат или смысл данных.

Это не «правило только для LLM». Такие контракты существовали в API и
интеграциях до агентов. Для агента они особенно важны: модель выбирает ход,
а contract ограничивает допустимые входы, выходы и последствия этого хода.

## Граница текущего spike

| Свойство | Зафиксированное значение |
| --- | --- |
| Модель | `gemini-3.5-flash-lite` через Google ADK `2.10.0` |
| Вход модели | incident event с `incident_id`, `device_id`, `symptom`; без `attachment_id` |
| Инструменты | Ровно `get_device` и `run_diagnostic` |
| Режим | Read-only: ни один tool не меняет устройство, инцидент или внешний сервис |
| Состояние | Только in-memory session/run record; это не product persistence |

## Domain entities

### Incident input

Минимальный контекст, с которого начинает модель.

| Поле | Тип | Значение/правило |
| --- | --- | --- |
| `incident_id` | string | Внешний идентификатор инцидента; в spike `INC-2026-00421` |
| `device_id` | string | Идентификатор устройства, например `POS-KZN17-03` |
| `symptom` | string | Наблюдаемый симптом, не диагностический вывод |

`attachment_id` **не является** полем initial input. Он может появиться только
в результате lookup-инструмента.

### Device

`Device` — объект оборудования, который известен по `device_id`. В текущем
fixture он связан с сетевым attachment. В будущем источник может стать ITSM/CMDB
API, но его внешний contract не должен меняться от замены хранилища.

### Attachment

`Attachment` — диагностируемое соединение/интерфейс устройства. Его ID является
результатом `get_device` и обязательным входом `run_diagnostic`. Эта связь —
главный data dependency spike.

### Diagnostic observation

Read-only снимок состояния attachment, а не команда на исправление. Текущие
поля: `attachment_id`, `diagnostic`, `observed_state`, `ok`.

## Tool contracts

### `get_device(device_id)`

Назначение: найти устройство и его диагностируемый attachment.

| Вход | Тип | Правило |
| --- | --- | --- |
| `device_id` | string | Непустой известный идентификатор устройства |

Успешный результат:

```json
{
  "ok": true,
  "device_id": "POS-KZN17-03",
  "attachment_id": "ATT-KZN17-POS03-NIC"
}
```

Ошибочный результат в production-версии должен быть структурированным, без
исключения формата: `{"ok": false, "error": {"code": "DEVICE_NOT_FOUND",
"message": "..."}}`. В spike fixtures пока заранее известны, но этот error
shape уже считается зафиксированным для следующей реализации.

### `run_diagnostic(attachment_id)`

Назначение: прочитать диагностическое наблюдение по attachment.

| Вход | Тип | Правило |
| --- | --- | --- |
| `attachment_id` | string | Должен быть фактически возвращён предыдущим `get_device` в том же run |

Успешный результат:

```json
{
  "ok": true,
  "attachment_id": "ATT-KZN17-POS03-NIC",
  "diagnostic": "LINK_DOWN",
  "observed_state": "network interface has no carrier"
}
```

Ошибочный shape для следующей фазы: `ATTACHMENT_NOT_FOUND`, `DIAGNOSTIC_UNAVAILABLE`
или `UPSTREAM_UNAVAILABLE` внутри `error.code`; вызывающий код не должен
парсить человеческий `message`, чтобы принять решение.

## Инварианты исполнения

1. Agent получает только incident event и не получает hidden `attachment_id`.
2. Модель, а не приложение, выбирает вызовы tools.
3. В acceptance run ровно два вызова: сначала `get_device`, затем
   `run_diagnostic`.
4. Аргумент второго вызова равен `attachment_id` из фактического результата
   первого вызова, а не заранее вставленной константе.
5. Tools read-only; никакой remediation, approval или mutation не разрешены.
6. Trace хранит tool calls/results и final answer, но не model thought content.

## Что будет меняться, а что — нет

- Можно заменить fixture на CMDB, NMS или ITSM adapter, если сохраняются имена
  tools, входные поля, response/error shapes и read-only семантика.
- Можно расширить сущности полями (site, owner, timestamps), но обязательные
  поля выше нельзя молча удалить или переименовать.
- Mutation tools, approvals, SLA/state machine и persistent incident timeline
  — это отдельные последующие contracts, не часть этого spike.

## Evidence фиксации

В Northflank 4 октября 2026 года выполнены три внешних `POST /spike/runs`.
Во всех ответах `validation.passed` был `true`, а наблюдаемая цепочка была:
`get_device(POS-KZN17-03)` → `ATT-KZN17-POS03-NIC` →
`run_diagnostic(ATT-KZN17-POS03-NIC)`. Сгенерированный безопасный отчёт хранится
локально в игнорируемом Git `results/phase2-northflank-20261004T000427Z.json`.
