# ALP ITSM Agent — Handoff v5.4

Дата обновления: 3 октября 2026 года. Этот файл заменяет в handoff v5.3 только статус и результаты Фазы 1; решения по архитектуре и roadmap из v5.3 остаются в силе.

## Что было сделано

В репозитории реализован минимальный local spike на **Google ADK Python function tools**, а не старый Dify/HTTP механизм:

- Python `3.12.14`, Google ADK `2.10.0`, `pytest` `8.4.2` и Gemini `gemini-3.5-flash-lite` закреплены в `.python-version`, `requirements.txt` и коде;
- добавлен один `Agent` с ровно двумя read-only function tools: `get_device(device_id)` и `run_diagnostic(attachment_id)`;
- initial input содержит только `incident_id`, `device_id` и symptom — не содержит `attachment_id` и не получает его из скрытого runtime context;
- `get_device` возвращает `ATT-KZN17-POS03-NIC`; только Gemini должен передать это значение второму tool;
- runner использует native `InMemorySessionService` и `Runner.run_async`, сохраняет tool-call/result trace и программно проверяет порядок, число вызовов и аргумент второго вызова;
- traces не содержат chain-of-thought: сохраняются только tool calls, tool results, final answer и error facts.

Код расположен в `phase1_adk_spike/`; unit-проверки — в `tests/test_phase1_adk_spike.py`. Старый Dify code не удалялся и не считается реализацией текущей Фазы 1.

## Результат реальной проверки на этой машине

Локальная проверка кода прошла: `5 passed` (`pytest`) и Python-модули компилируются. В окружении установлены `google-adk==2.10.0` под Python `3.12.14` и model pin `gemini-3.5-flash-lite`.

3 октября 2026 года выполнены **три независимых реальных Gemini runs**. Summary сохранён как `results/phase1-20261003T200708Z.json`; связанные audit-safe traces:

- `traces/phase1-01-8ad59a3d.json`;
- `traces/phase1-02-f6368a8b.json`;
- `traces/phase1-03-95066547.json`.

Каждый run завершился без model/tool error, получил fresh ADK session и прошёл `validation.passed: true`. Во всех трёх случаях Gemini самостоятельно сделал ровно следующую последовательность:

1. `get_device(device_id="POS-KZN17-03")`;
2. прочитал из result `attachment_id="ATT-KZN17-POS03-NIC"`;
3. `run_diagnostic(attachment_id="ATT-KZN17-POS03-NIC")`.

Initial input во всех запусках не содержал `attachment_id`. Второй аргумент проверяется не по предсказанному hardcoded sequence, а по фактическому result первого tool call. Таким образом доказана native ADK + Gemini dependent multi-step цепочка в одной сессии на каждом run.

## Стабильность и обнаруженные проблемы

- В доступной выборке: **3/3 успешных independent runs**; это достаточно для acceptance gate текущего узкого spike, но не является production reliability claim.
- ADK при построении function schema написал warning: `FeatureName.JSON_SCHEMA_FOR_FUNC_DECL is enabled` и помечает эту возможность как experimental. На tool schema, вызовы и results это не повлияло, но при обновлении ADK spike нужно повторить.
- Первая попытка из sandbox завершилась `ConnectError` до model response: sandbox блокировал исходящее соединение. После разрешённого прямого доступа к Gemini три прогона прошли. Это ограничение среды запуска, не ошибка Gemini tool calling и не проблема ключа.
- Не обнаружены `429`, malformed function call, лишний/repeated tool call, остановка после первого result или provider/model error.

## Зафиксированные риски и наблюдения

- ADK `2.10.0` — быстро развивающаяся 2.x-линейка; закрепление обязательно, любые будущие обновления должны сопровождаться повторным live spike.
- Gemini 3.5 Flash-Lite — стабильная, ориентированная на throughput/cost модель. Её зависимая цепочка подтверждена на текущем API key тремя runs; при смене model pin, ADK version или provider configuration spike нужно повторить.
- `InMemorySessionService` выбран только для spike. Он намеренно не является решением persistence для следующих фаз.
- Блокирующий фактор — доступ к Gemini API, а не кодовая архитектура. Никакой обходной scripted sequence добавлен не был.

## Решение о статусе

**Фаза 1: ЗАВЕРШЕНА.** Закреплены версии, реализован минимальный ADK agent с ровно двумя read-only function tools, сохранены результаты/trace трёх реальных runs и подтверждён model-selected dependent multi-step tool calling. Можно переходить к Фазе 2 по исходному roadmap, не расширяя этот spike в БД, UI, SSE, approvals или Northflank в рамках Фазы 1.
