# ALP ITSM Agent — Handoff v5.5

Дата обновления: 4 октября 2026 года. Этот файл дополняет v5.4 результатами
Фазы 2 и фиксирует tool/domain contracts после её PASS. Решения по большому
Scenario 1 из v5.3 не заменяются этим узким runtime spike.

## Итог

**Фаза 2: ЗАВЕРШЕНА.** Минимальный ADK/Gemini spike реально запущен вне
локальной машины на Northflank, получил credential через secret file и трижды
выполнил model-selected цепочку двух зависимых read-only tools.

Публичный URL runtime: `https://p01--adk-spike--yxz5y8myjdln.code.run/`.
Он предназначен только для верификации spike, а не как production API.

## Что добавлено в репозиторий

- `phase2_backend/` — минимальная FastAPI HTTP-оболочка без БД, UI, SSE,
  approvals или product workflow;
- `Dockerfile` и `.dockerignore` для Python `3.12.14` runtime;
- `POST /spike/runs`, который запускает native ADK session и возвращает
  audit-safe trace/result; `GET /health` не раскрывает ключ, а сообщает только
  факт его доступности;
- health/OpenAPI test и проверка bare secret-file fallback;
- `docs/contracts/PHASE_2_TOOL_AND_DOMAIN_CONTRACTS.md` — зафиксированные
  tool/domain contracts, error shapes и инварианты следующей фазы.

Секрет в Git не попал: `.env`, `results/` и `traces/` игнорируются. В
Northflank ключ смонтирован в `/app/.env`; приложение поддерживает обычный
dotenv-формат и bare secret-file format, не логируя его значение.

## Runtime и версии

| Компонент | Зафиксированное значение |
| --- | --- |
| Python | `3.12.14` |
| Google ADK | `2.10.0` |
| Gemini | `gemini-3.5-flash-lite` |
| FastAPI | `0.141.1` |
| Uvicorn | `0.54.0` |
| Northflank runtime | `nf-compute-10`, 0.1 shared vCPU / 256 MB |

## Реальная внешняя проверка

4 октября 2026 года Northflank readiness стал passing; публичный `/health`
вернул `status: ok` и `google_api_key_configured: true`.

Затем выполнены три независимых `POST /spike/runs`. Каждый вернул
`status: completed` и `validation.passed: true`. Во всех трёх Gemini сделал
ровно:

1. `get_device(device_id="POS-KZN17-03")`;
2. получил из реального tool result `attachment_id="ATT-KZN17-POS03-NIC"`;
3. `run_diagnostic(attachment_id="ATT-KZN17-POS03-NIC")`.

Таким образом initial input не содержал attachment ID, application не
вызвало tools за модель и второй аргумент был связан с первым result.
Сгенерированный внешний report сохранён локально в игнорируемом Git файле
`results/phase2-northflank-20261004T000427Z.json`.

## Обнаруженные проблемы и решение

1. Первичная сборка Northflank упала не из-за платформы: `fastapi==0.142.2`
   требовал `opentelemetry-api>=1.44`, а `google-adk==2.10.0` ограничивает его
   `<=1.42.1`. Версия FastAPI заменена на новейшую совместимую `0.141.1`;
   `pip check` чистый, локально `8 passed`, повторная сборка прошла.
2. Первый mounted secret file не давал переменную окружения. Добавлен узкий
   fallback для одного bare secret value; он не печатает и не сохраняет ключ.
   После redeploy `/health` подтвердил доступность ключа и реальные Gemini
   runs прошли.
3. В ADK остаётся warning об experimental JSON-schema function declarations,
   замеченный ещё в Фазе 1. Это не сломало tools, но live regression spike
   обязателен после обновления ADK или model pin.

## Ограничения и следующий шаг

- Сервис публичен только как временный verification endpoint; у него нет
  auth, rate limiting, persistent storage или production observability.
- In-memory runs исчезают при restart и намеренно не являются хранилищем
  Scenario 1.
- 3/3 — evidence acceptance spike, не статистическое доказательство
  production reliability.

Следующий допустимый шаг: проектировать настоящее основание Scenario 1,
опираясь на уже зафиксированные contracts. Начать с adapter boundaries для
реальных CMDB/ITSM/NMS, error taxonomy, entity state transitions и отдельного
mutation/approval contract. Не добавлять mutation tool в этот spike без
нового explicit contract и approval policy.
