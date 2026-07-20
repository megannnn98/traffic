# План реализации: сервис сбора и текстового описания пробок Алматы

> **Устарело.** Проект реализован по этому плану на Yandex Distance Matrix API, но позже
> мигрировал на **TomTom Flow Segment Data API** (см. `README.md` и `CLAUDE.md`). Факты об
> API и разделы 6, 8, 9 ниже относятся к Yandex и **не отражают текущую реализацию**.
> Документ оставлен как исторический контекст решений (этапы, тесты, критерии готовности
> по-прежнему в целом применимы), а не как источник истины по API.

Этот документ — самодостаточное задание для AI-исполнителя. Вся необходимая информация
(проверенные факты об API, архитектурные решения, полное ТЗ, этапы с критериями проверки)
содержится здесь. Доступ к вебу и к исходной переписке не требуется.

---

## 1. Роль и цель

Ты — Python-разработчик. Реализуй CLI-программу, которая:

1. Загружает список контрольных дорожных участков Алматы из YAML-конфигурации.
2. Регулярно запрашивает текущее время движения по ним через **официальный Yandex Distance Matrix API**.
3. Сохраняет историю измерений в SQLite.
4. Вычисляет степень загруженности каждого участка относительно базового времени свободного движения.
5. Формирует JSON-снимок обстановки, русский текст для LLM и краткую сводку проблемных участков.
6. Работает в двух режимах: один опрос (`collect`) и постоянный сборщик (`run`).

**Запрещено**: парсить сайт, приложение, тайлы или внутренние запросы Яндекс Карт. Только официальный API.

Целевая ОС — Arch Linux. Python 3.12+.

---

## 2. Проверенные факты о Yandex Distance Matrix API (source of truth)

Эти факты проверены по официальной документации (`yandex.com/maps-api/docs/distancematrix-api/`)
в июле 2026. Используй их как данность, не выдумывай другие параметры.

- **Эндпоинт (синхронный)**: `GET https://api.routing.yandex.net/v2/distancematrix`
- **Авторизация**: query-параметр `apikey` (ключ из кабинета разработчика Yandex Maps API).
- **Обязательные параметры**:
  - `origins` — точки отправления: `latitude,longitude` в десятичных градусах, пары разделяются `|`;
  - `destinations` — точки назначения, тот же формат.
- **Опциональные параметры**:
  - `mode` — режим движения; значения: `driving` (по умолчанию), `truck`, `walking`, `transit`, `bicycle`, `scooter`. Использовать `driving`.
  - `departure_time` — UNIX timestamp времени отправления, **не может быть в прошлом**; учитывает прогноз пробок; работает для `driving`.
- **Формат ответа** (JSON):
  - `rows[i].elements[j]` — маршрут от `origins[i]` к `destinations[j]`; порядок строго соответствует порядку в запросе;
  - `elements[j].status` — `"OK"` (маршрут построен) или `"FAIL"` (маршрут не найден, например рядом с точкой нет дороги);
  - `elements[j].duration.value` — длительность в **секундах**;
  - `elements[j].distance.value` — расстояние в **метрах**.
- **Важно**: ответ — всегда **полный декартов продукт** origins × destinations. Независимые пары точек одним запросом передать нельзя.
- **Лимиты**: максимум 100 элементов матрицы на запрос (например, 10×10 можно, 50×10 нельзя); максимум 40 запросов в секунду.
- **HTTP-ошибки**: `400` — отсутствуют обязательные параметры; `401` — неверный или отсутствующий ключ; `429` — превышение лимита запросов; `500`/`504` — ошибка сервера. Тело ошибки содержит поле `errors` — массив текстовых сообщений.

Если фактическое поведение API отличается от описанного — официальная документация главнее;
зафиксируй расхождение в README.

---

## 3. Зафиксированные архитектурные решения (исполнять, не обсуждать)

1. **Один HTTP-запрос = один участок** (матрица 1×1: один origin, один destination).
   Причина: API возвращает только декартов продукт, а участки — независимые направленные пары точек.
   Сопоставление ответа с `segment_id` при этом тривиально.
2. Параллелизм запросов ограничить через `asyncio.Semaphore(5)`.
3. В каждом запросе передавать `departure_time` = текущее время (UNIX). Если API отклонит значение
   как «в прошлом» (рассинхронизация часов), допустимо добавить небольшой сдвиг вперёд (например +60 с).
4. Время: внутри программы — только timezone-aware `datetime` в UTC; при сохранении в БД и выводе —
   ISO 8601 в `Asia/Almaty` (через `zoneinfo`).
5. `raw_response` измерения — JSON-элемент ответа по данному участку (не весь HTTP-ответ).
6. Пороги классификации загруженности — именованные константы в одном модуле `congestion.py`.
7. Пакетирование: src-layout, `pyproject.toml`, console-script entry point `almaty-traffic`.
8. Никакого глобального изменяемого состояния; зависимости передаются явно (настройки, соединение с БД, клиент).

---

## 4. Технологии

- Python 3.12+
- `httpx` (HTTP, `AsyncClient`), `pydantic` v2 (модели), `pydantic-settings` (env),
  `PyYAML` (конфиг), стандартный `sqlite3` (или `aiosqlite`), `typer` (CLI)
- `pytest` (тесты), `ruff` (линт + формат), `mypy` (типы)
- Без тяжёлых веб-фреймворков.

---

## 5. Структура проекта

```text
almaty-traffic/
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
├── config/
│   └── segments.yaml
├── data/
│   └── .gitkeep
├── src/
│   └── almaty_traffic/
│       ├── __init__.py
│       ├── cli.py
│       ├── settings.py
│       ├── models.py
│       ├── yandex_client.py
│       ├── collector.py
│       ├── database.py
│       ├── congestion.py
│       ├── formatter.py
│       └── scheduler.py
└── tests/
    ├── test_congestion.py
    ├── test_formatter.py
    ├── test_database.py
    └── test_yandex_client.py
```

Структуру можно улучшать, если решение остаётся простым.

---

## 6. Конфигурация

### Переменные окружения (`.env`, через `pydantic-settings`)

```env
YANDEX_API_KEY=your_api_key
TRAFFIC_DATABASE_PATH=data/traffic.sqlite3
TRAFFIC_SEGMENTS_CONFIG=config/segments.yaml
TRAFFIC_REQUEST_TIMEOUT_SECONDS=15
TRAFFIC_COLLECTION_INTERVAL_SECONDS=300
TRAFFIC_TIMEZONE=Asia/Almaty
```

### `config/segments.yaml`

```yaml
segments:
  - id: abai_nazarbayev_seifullin_east
    road: проспект Абая
    direction: восток
    from_name: проспект Назарбаева
    to_name: проспект Сейфуллина
    origin:
      latitude: 43.2381
      longitude: 76.9452
    destination:
      latitude: 43.2384
      longitude: 76.9281
    free_flow_duration_seconds: 240
    enabled: true

  - id: al_farabi_dostyk_nazarbayev_west
    road: проспект Аль-Фараби
    direction: запад
    from_name: проспект Достык
    to_name: проспект Назарбаева
    origin:
      latitude: 43.2081
      longitude: 76.9600
    destination:
      latitude: 43.2110
      longitude: 76.9420
    free_flow_duration_seconds: 300
    enabled: true
```

Координаты демонстрационные — в README явно указать, что реальные точки надо проверить вручную
в Яндекс Картах. Участок направленный; обратное направление — отдельная запись.

---

## 7. Модели данных (`models.py`, pydantic)

Минимум: `Coordinate`, `TrafficSegment`, `RouteMeasurement`, `CongestionResult`, `TrafficSnapshot`.

`RouteMeasurement`: `timestamp`, `segment_id`, `distance_meters`, `duration_seconds`, `status`,
`error_message`, `raw_response`.

`CongestionResult`: `segment_id`, `duration_seconds`, `free_flow_duration_seconds`,
`delay_seconds`, `congestion_ratio`, `congestion_level`.

Уровни загруженности (enum): `free`, `light`, `dense`, `traffic_jam`, `severe_traffic_jam`, `unknown`.

---

## 8. API-клиент (`yandex_client.py`)

```python
class YandexDistanceMatrixClient:
    async def get_routes(
        self,
        segments: list[TrafficSegment],
    ) -> list[RouteMeasurement]: ...
```

Требования:

1. `httpx.AsyncClient`, таймаут из настроек.
2. Один запрос 1×1 на участок (см. раздел 3), `asyncio.Semaphore(5)`.
3. `mode=driving`, `departure_time` = текущее время.
4. Проверять HTTP-код и структуру ответа (наличие `rows[0].elements[0]` и т.д.).
5. Обрабатывать: таймаут; сетевую ошибку; 401 (неверный ключ); 429 (квота); `status="FAIL"`
   (нет маршрута); повреждённый JSON; частично успешный цикл (часть участков упала).
6. Ошибка одного участка **не** прерывает цикл: для неудачного участка вернуть `RouteMeasurement`
   со `status` ошибки и `error_message`, остальные обработать.
7. В логах и сообщениях об ошибках API-ключ никогда не выводить (маскировать URL при логировании).

---

## 9. База данных (`database.py`, SQLite)

Таблицы (создавать автоматически при старте, если отсутствуют):

```sql
CREATE TABLE IF NOT EXISTS segments (
  id TEXT PRIMARY KEY,
  road TEXT NOT NULL,
  direction TEXT NOT NULL,
  from_name TEXT NOT NULL,
  to_name TEXT NOT NULL,
  origin_lat REAL NOT NULL,
  origin_lon REAL NOT NULL,
  destination_lat REAL NOT NULL,
  destination_lon REAL NOT NULL,
  free_flow_duration_seconds INTEGER,
  enabled INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS measurements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  segment_id TEXT NOT NULL,
  distance_meters INTEGER,
  duration_seconds INTEGER,
  status TEXT NOT NULL,
  error_message TEXT,
  raw_response TEXT,
  FOREIGN KEY(segment_id) REFERENCES segments(id)
);

CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  json_payload TEXT NOT NULL,
  text_payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_measurements_timestamp
ON measurements(timestamp);

CREATE INDEX IF NOT EXISTS idx_measurements_segment_timestamp
ON measurements(segment_id, timestamp);
```

Время хранить строкой ISO 8601 с часовым поясом `Asia/Almaty`.

---

## 10. Вычисление загруженности (`congestion.py`)

```text
congestion_ratio = current_duration_seconds / free_flow_duration_seconds
delay_seconds    = max(0, current_duration_seconds - free_flow_duration_seconds)
```

Классификация (границы — именованные константы в этом модуле):

```text
ratio < 1.20          -> free
1.20 <= ratio < 1.50  -> light
1.50 <= ratio < 2.00  -> dense
2.00 <= ratio < 3.00  -> traffic_jam
ratio >= 3.00         -> severe_traffic_jam
```

Если базовое время отсутствует или равно нулю: `congestion_level = unknown`, `congestion_ratio = null`.
В README и текстах не называть эту оценку официальным баллом пробок Яндекса.

---

## 11. Калибровка базового времени

Команда `almaty-traffic calibrate [--days 14] [--write-config]`.

Для каждого участка: взять измерения за последние N дней в окне 02:00–05:00 местного времени
(`Asia/Almaty`), рассчитать базовое время как **20-й перцентиль** длительности. Алгоритм —
отдельная чистая функция, покрытая тестами.

Без `--write-config` — только вывести рассчитанные значения. С флагом — перезаписать YAML,
**предварительно создав резервную копию** файла.

---

## 12. JSON-снимок

```json
{
  "timestamp": "2026-07-20T10:15:00+05:00",
  "city": "Алматы",
  "source": "Yandex Distance Matrix API",
  "segments": [
    {
      "id": "abai_nazarbayev_seifullin_east",
      "road": "проспект Абая",
      "direction": "восток",
      "from": "проспект Назарбаева",
      "to": "проспект Сейфуллина",
      "distance_meters": 3100,
      "duration_seconds": 720,
      "free_flow_duration_seconds": 240,
      "delay_seconds": 480,
      "congestion_ratio": 3.0,
      "congestion_level": "severe_traffic_jam"
    }
  ],
  "summary": {
    "total_segments": 20,
    "successful_segments": 19,
    "failed_segments": 1,
    "traffic_jam_segments": 4,
    "severe_traffic_jam_segments": 2
  }
}
```

Сортировка участков: по уровню загруженности (от тяжёлого к свободному), внутри уровня — по задержке.

---

## 13. Текст для LLM (`formatter.py`)

Отдельный класс или чистые функции. Три режима:

1. **Полный** — естественный русский текст, участки сгруппированы: сильные пробки; пробки;
   плотное движение; небольшое замедление; свободное движение. Участки с ошибкой выводить
   отдельной строкой («Не удалось получить данные для N участков»), **не** как свободные.
2. **Краткий** (`--only-congested`) — только проблемные участки.
3. **Машинный** — `key=value` строки без художественных формулировок:

```text
timestamp=2026-07-20T10:15:00+05:00
city=Алматы
segment=abai_nazarbayev_seifullin_east
road=проспект Абая
direction=восток
duration_min=12
baseline_min=4
delay_min=8
congestion_level=severe_traffic_jam
```

Пример полного текста:

```text
Дорожная обстановка в Алматы на 20 июля 2026 года, 10:15.

Сильные пробки:
— Проспект Абая, направление на восток, от Назарбаева до Сейфуллина. Поездка занимает 12 минут вместо обычных 4 минут. Задержка около 8 минут.

Плотное движение:
— Проспект Аль-Фараби, направление на запад, от Достык до Назарбаева. Задержка около 6 минут.

Свободное движение:
— Восточная объездная дорога, направление на север.

Не удалось получить данные для одного участка.
```

Обязательно корректное склонение минут: 1 минута, 2–4 минуты, 5+ минут
(с учётом 11–14 → «минут», 21 → «минута» и т.д.).

---

## 14. CLI (`cli.py`, typer)

| Команда | Что делает |
|---|---|
| `validate-config` | проверяет YAML: уникальность ID, корректность координат (широта −90…90, долгота −180…180), обязательные поля, положительное базовое время, наличие ≥1 активного участка |
| `collect` | один цикл: конфиг → API → запись измерений → расчёт загруженности → запись snapshot → краткая сводка в stdout; при полном отсутствии связи — ненулевой exit code |
| `run [--interval 300]` | циклический сбор с интервалом (по умолчанию из настроек); корректное завершение по SIGINT/SIGTERM; ошибки цикла не останавливают процесс |
| `report [--format text\|json\|llm] [--only-congested]` | последняя сводка из БД; если данных нет — понятное сообщение, не traceback |
| `history <segment_id> --hours 24` | история измерений участка |
| `calibrate [--days 14] [--write-config]` | калибровка базового времени (раздел 11) |

Глобальная опция `--log-level DEBUG|INFO|WARNING` (стандартный `logging`).

Логировать: начало/конец цикла, число участков, число успешных запросов, ошибки API,
длительность цикла, путь к БД, время следующего запуска. **Ключ API не логировать.**

---

## 15. Обработка ошибок

Программа не должна падать целиком при: ошибке одного маршрута; недоступности API; таймауте;
повреждённой записи в ответе; невозможности записать один snapshot; отсутствии базового времени;
пустой БД при `report`.

При полном отсутствии связи: записать неуспешные измерения; вывести понятное сообщение;
в `collect` завершиться с ненулевым кодом; в `run` продолжить после интервала.

---

## 16. Этапы реализации (работать строго последовательно)

После каждого этапа: запустить тесты, исправить ошибки, кратко описать сделанное.

| Этап | Задача | Критерий проверки (verify) |
|---|---|---|
| 1 | Каркас: pyproject, `.gitignore`, `.env.example`, `settings.py`, `models.py`, загрузка YAML, `validate-config` | `pip install -e ".[dev]"` проходит; `almaty-traffic validate-config` работает на примере YAML; тесты валидации YAML зелёные |
| 2 | `yandex_client.py` + mock-ответы (`httpx.MockTransport`) | тесты: успешный ответ, 401, 429, таймаут, FAIL, битый JSON, частичный успех |
| 3 | `database.py`: схема, индексы, автосоздание, запись/чтение измерений и snapshot | тесты БД на временном файле/`:memory:` |
| 4 | `congestion.py`: формулы, константы порогов | тесты всех границ (1.19/1.20/1.49/1.50/1.99/2.0/2.99/3.0), `unknown`, отрицательная задержка → 0 |
| 5 | `formatter.py`: JSON-снимок, полный/краткий/машинный текст, склонение минут, сортировка | тесты формата, склонения (1/2/5/11/21/25), сортировки, JSON-структуры |
| 6 | `cli.py`: `validate-config`, `collect`, `report`, `history` | ручной прогон `collect` с mock/реальным ключом; `report --format json` — валидный JSON |
| 7 | `scheduler.py`: режим `run`, интервал, SIGINT/SIGTERM | ручной запуск: цикл повторяется, Ctrl+C завершает чисто, ошибка цикла не убивает процесс |
| 8 | Калибровка: перцентиль, ночное окно, `--write-config` + backup YAML | тесты калибровки на синтетической истории; backup создаётся |
| 9 | README, ruff, mypy, покрытие | `pytest` зелёный, покрытие ≥85%; `ruff check .` чисто; `mypy src` чисто |

---

## 17. Тесты (без реальных запросов к API — только mock)

Покрыть: (1) `congestion_ratio`; (2) все границы классификации; (3) отсутствие базового времени;
(4) отрицательная задержка; (5) склонение минут; (6) русский текст; (7) сортировка;
(8) JSON; (9) создание БД; (10) запись/чтение измерений; (11) успешный ответ API; (12) HTTP 401;
(13) HTTP 429; (14) таймаут; (15) частично успешный ответ; (16) калибровка; (17) валидация YAML.

Покрытие ≥ 85%.

---

## 18. README

Содержит: назначение; ограничения подхода; предупреждение, что это **не** официальный балл пробок
Яндекса; как получить ключ Yandex Maps API; установка на Arch Linux
(`python -m venv .venv && source .venv/bin/activate && python -m pip install -e ".[dev]"`);
настройка `.env`; пример `segments.yaml` с предупреждением о демо-координатах; запуск `collect`
и `run`; примеры JSON и LLM-текста; описание схемы БД; запуск тестов, ruff, mypy;
зафиксированные расхождения с ТЗ (если обнаружатся при работе с реальным API).

---

## 19. Критерии готовности

- `validate-config` проверяет YAML;
- `collect` получает (или имитирует в тестах) данные и сохраняет в SQLite;
- `run` выполняет регулярный сбор и корректно завершается по сигналам;
- `report --format json` выдаёт валидный JSON; `report --format llm` — понятный русский текст;
- ошибка одного участка не ломает цикл;
- API-ключ не попадает в логи и в Git;
- `pytest` проходит, покрытие ≥85%; `ruff check .` и `mypy src` чистые;
- README позволяет запустить проект с нуля.

---

## 20. Ограничения первого релиза (НЕ делать)

Веб-интерфейс; Telegram-бот; PostgreSQL; Docker; карты и визуализация; машинное обучение;
прогнозирование; автоматический поиск всех улиц Алматы; парсинг Яндекс Карт.

---

## 21. Качество кода

Полная типизация; понятные имена; небольшие функции; разделение слоёв HTTP/БД/вычисления/форматирование;
без глобального изменяемого состояния; без API-ключей в репозитории; минимум дублирования;
docstring для публичных классов и сложных функций; комментарии только там, где код не объясняет
себя сам; не усложнять архитектуру паттернами без необходимости.
