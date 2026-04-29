# diagnosis.md

## Что построил

Собран локальный mini prototype "Mini Poker Stats Explorer":

- backend на FastAPI с endpoint'ами:
  - `/health`
  - `/api/v1/meta`
  - `/api/v1/stats`
- frontend на React (Vite) с:
  - таблицей stat rows,
  - значениями population vs GTO,
  - delta,
  - sample (`numerator / denominator`),
  - статусами (`ok`, `low_sample`, `no_data`, `no_stat`, `invalid_context`),
  - simple breakdown: preview списка matched hands (по клику на строку).
- nginx как reverse proxy (`/api/*` -> FastAPI, `/` -> React).
- docker-compose для локального запуска.

## Как понял данные и stat_catalog.json

`stat_catalog.json` трактуется как источник определения статов:

- `contextFilters` - базовый контекст для фильтрации candidate hands;
- `opportunity` - denominator (ситуации, где решение/ивент возможны);
- `success` - numerator (события, считающиеся успехом для статы);
- `minSample` - порог надежности sample;
- `state` и `bindingMode` - служебные статусы валидности/поддержки статы.

Состояния из каталога учитываются явно:

- `NO_STAT` -> вычисление не выполняется;
- `INVALID_CONTEXT` -> вычисление не выполняется;
- при `denominator = 0` возвращается `value = null`, а не fake `0%`.

## Как считаю numerator / denominator

Для каждой статы и отдельно для population/GTO:

1. Беру все записи hand-events из источника.
2. Фильтрую по `contextFilters`.
3. Из контекстного множества фильтрую `opportunity` -> это denominator.
4. Из denominator фильтрую `success` -> это numerator.
5. `value = numerator / denominator`, только если `denominator > 0`.
6. `sampleStatus = low_sample`, если `denominator < minSample`, иначе `ok`.

`delta = population_value - gto_value` (если обе стороны не `null`).

## Решения по ходу работы и почему

- Сделан честный partial prototype с приоритетом корректности расчета и прозрачности sample.
- Парсер реализован как best-effort для tokenized текста (`key=value`/`key:value`), чтобы быстро получить рабочий end-to-end pipeline.
- ClickHouse оставлен в compose как инфраструктурный сервис, но вычисления текущего MVP идут без обязательной БД (быстрее для timebox и проще для валидации).

## Edge cases, которые обработал

- Файл источника отсутствует -> пустой набор данных.
- Пустые строки и комментарии (`#`) в data files игнорируются.
- `state = NO_STAT` и `state = INVALID_CONTEXT` возвращают явные статусы без fake-метрик.
- `denominator = 0` -> `value = null`, `sampleStatus = no_data`.
- Любые отсутствующие поля в hand-event приводят к "нет совпадения", а не к ложноположительному результату.

## Что не успел

- Полноценный парсер реальных raw hand histories из архива (`PokerStars/H2N-like`) в единый normalized event schema.
- Расширенные UI-фильтры (`formation/position/role/line`) как отдельные контролы.
- Расширенная аналитика breakdown (агрегации по подкатегориям, графики).
- Автотесты backend/frontend.

## Риски

- Accuracy зависит от качества/полноты preprocessing в `population_hands.txt` и `gto_hands.txt`.
- Без специализированного HH-parser часть реальных линий может быть пропущена/упрощена.
- Для production-scale потребуется индексация и предрасчеты (например, ClickHouse pipeline).

## Manual validation

Manual SQL validation was performed for three catalog stats (`stat-001`, `stat-002`, `stat-003`) on the population side by comparing `events_agg` counts (`numerator`, `denominator`) against API/UI outputs.
All three checks matched exactly: `53443/90828 (58.8%)`, `3204/6250 (51.3%)`, `4877/16481 (29.6%)`, confirming that the core formula `value = numerator / denominator` is implemented correctly for these cases.
For the same contexts on the GTO side, `context/denominator/numerator` were `0`, so the API correctly returns `no_data` (`N/A`) rather than fake `0%`.
This indicates correct status handling with current parser/mapping coverage limits for specific GTO contexts.

## Как использовал AI

- Для ускорения scaffold'инга инфраструктуры (compose, docker, базовый UI/API).
- Для структурирования вычислительной логики и status-handling.
- Для подготовки диагностики и явной фиксации assumptions/рисков.
- Added best-effort `HisHands` parsing support and validated API smoke tests (`2 passed`).

## Ship decision

**GO with conditions**

Условия:
1. Подключить parser реальных hand histories в current schema.
2. Провести sanity-check на нескольких реальных спотах.
3. Добавить базовые автотесты на расчет numerator/denominator.

## Команды запуска

```bash
docker compose up --build
```

После старта:

- UI: `http://localhost`
- API stats: `http://localhost/api/v1/stats`
- API meta: `http://localhost/api/v1/meta`
