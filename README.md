# almaty-traffic

CLI-сервис сбора и текстового описания пробок Алматы через [TomTom Flow Segment Data API](https://developer.tomtom.com/traffic-api/documentation/traffic-flow/flow-segment-data).

Для каждого контрольного дорожного участка получает реальные данные о скорости, времени движения и уровне загруженности. История хранится в SQLite. Результат — JSON-снимок и текст на русском языке, готовый для подачи в LLM.

## Возможности

- **Сбор данных** — разовый или циклический опрос TomTom API, параллельные запросы с семафором
- **Загруженность** — классификация по 5 уровням: свободно / лёгкая / плотная / пробка / сильная пробка
- **История** — все измерения сохраняются в SQLite для анализа
- **Калибровка** — автоматическое определение базового (свободного) времени по ночным замерам
- **Форматы вывода** — JSON, текст для LLM
- **Безопасность** — API-ключ никогда не попадает в Git (`.env` в `.gitignore`), маскируется в логах

## Получение API-ключа

1. Зарегистрируйтесь на [developer.tomtom.com](https://developer.tomtom.com/)
2. Создайте приложение, выберите продукт **Flow Segment Data**
3. Скопируйте API-ключ
4. Бесплатный тариф: **2500 запросов/день** (Flow Segment Data)

## Установка

Требуется Python **3.12+**.

```bash
git clone https://github.com/megannnn98/traffic.git
cd traffic

python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Настройка

### 1. Переменные окружения

Скопируйте шаблон и заполните:

```bash
cp .env.example .env
```

| Переменная | По умолчанию | Описание |
|---|---|---|
| `TOMTOM_API_KEY` | — | API-ключ TomTom (**обязательно**) |
| `TRAFFIC_DATABASE_PATH` | `data/traffic.sqlite3` | Путь к файлу БД |
| `TRAFFIC_SEGMENTS_CONFIG` | `config/segments.yaml` | Путь к конфигурации участков |
| `TRAFFIC_REQUEST_TIMEOUT_SECONDS` | `15` | Таймаут HTTP-запроса к API |
| `TRAFFIC_COLLECTION_INTERVAL_SECONDS` | `300` | Интервал циклического сбора |
| `TRAFFIC_TIMEZONE` | `Asia/Almaty` | Часовой пояс для меток времени |

### 2. Участки дорог

Конфигурация в `config/segments.yaml`:

```yaml
segments:
  - id: abai_nazarbayev_seifullin_east       # уникальный ID
    road: проспект Абая                        # название дороги
    direction: восток                          # направление
    from_name: проспект Назарбаева             # от
    to_name: проспект Сейфуллина               # до
    origin:
      latitude: 43.2381                        # начальная точка
      longitude: 76.9452
    destination:
      latitude: 43.2384                        # конечная точка
      longitude: 76.9281
    free_flow_duration_seconds: 240            # базовое время (сек), опционально
    enabled: true                              # участвует в сборе
```

API-запрос отправляется для координат `origin`. `free_flow_duration_seconds` используется как fallback, когда TomTom не возвращает `freeFlowTravelTime`.

Валидация конфигурации:

```bash
almaty-traffic validate-config
```

## Команды

### `collect` — разовый сбор

```bash
almaty-traffic collect
almaty-traffic collect --config /path/to/segments.yaml
```

Собирает данные по всем активным (`enabled: true`) участкам, сохраняет в БД, генерирует снимок и выводит текст.

### `run` — циклический сбор

```bash
almaty-traffic run --interval 300
```

Запускает бесконечный цикл сбора с указанным интервалом (секунды). Корректно обрабатывает SIGINT/SIGTERM — завершает текущий цикл перед выходом.

### `report` — последний снимок

```bash
almaty-traffic report                    # текст для LLM (по умолчанию)
almaty-traffic report --format json      # JSON-снимок
almaty-traffic report --only-congested   # только проблемные участки
```

Читает последний снимок из БД и выводит в указанном формате.

### `history` — история измерений

```bash
almaty-traffic history abai_nazarbayev_seifullin_east --hours 24
```

Выводит все измерения указанного участка за последние N часов.

### `calibrate` — калибровка базового времени

```bash
almaty-traffic calibrate --days 14               # анализ без записи
almaty-traffic calibrate --days 14 --write-config # записать в segments.yaml
```

Анализирует ночные измерения (02:00–05:00) за указанный период и вычисляет медианное время проезда — оно считается базовым (свободное движение). С флагом `--write-config` обновляет `free_flow_duration_seconds` в YAML-конфиге.

## Уровни загруженности

Классификация основана на `congestion_ratio` — отношении текущего времени проезда к базовому (свободному):

| Уровень | Ratio | Описание |
|---|---|---|
| `free` | < 1.2 | Свободно |
| `light` | 1.2 – 1.5 | Лёгкая загруженность |
| `dense` | 1.5 – 2.0 | Плотное движение |
| `traffic_jam` | 2.0 – 3.0 | Пробка |
| `severe_traffic_jam` | > 3.0 | Сильная пробка |
| `unknown` | — | Нет данных |

Пороги определены как именованные константы в `congestion.py`.

## Форматы вывода

### JSON

```json
{
  "timestamp": "2026-07-20T10:15:00+05:00",
  "city": "Алматы",
  "source": "TomTom Flow Segment Data API",
  "segments": [
    {
      "id": "abai_nazarbayev_seifullin_east",
      "current_speed_kmh": 17,
      "free_flow_speed_kmh": 54,
      "current_travel_time_seconds": 420,
      "free_flow_travel_time_seconds": 140,
      "confidence": 0.91,
      "road_closure": false,
      "congestion_ratio": 3.0,
      "congestion_level": "severe_traffic_jam"
    }
  ],
  "summary": {
    "total_segments": 2,
    "successful_segments": 2,
    "failed_segments": 0,
    "traffic_jam_segments": 0,
    "severe_traffic_jam_segments": 1
  }
}
```

### Текст для LLM

```
Дорожная обстановка в Алматы на 20.07.2026 года, 10:15.

Сильные пробки:
— abai_nazarbayev_seifullin_east. Текущая скорость: 17 км/ч. Обычная скорость: 54 км/ч.
  Снижение скорости: 68%. Поездка: 7 мин вместо 2 мин.

Свободное движение:
— al_farabi_dostyk_nazarbayev_west. Текущая скорость: 55 км/ч. Обычная скорость: 60 км/ч.
  Снижение скорости: 8%. Поездка: 5 мин вместо 5 мин.
```

Участки группируются по уровню загруженности: сильные пробки, пробки, плотное движение, лёгкая загруженность, свободное движение.

## Схема БД

SQLite, три таблицы:

### `segments`

| Колонка | Тип | Описание |
|---|---|---|
| `id` | TEXT PK | ID участка |
| `road`, `direction`, `from_name`, `to_name` | TEXT | Описание участка |
| `origin_lat`, `origin_lon`, `destination_lat`, `destination_lon` | REAL | Координаты |
| `free_flow_duration_seconds` | INTEGER | Базовое время (сек) |
| `enabled` | INTEGER | Активен (0/1) |

### `measurements`

| Колонка | Тип | Описание |
|---|---|---|
| `id` | INTEGER PK | Автоинкремент |
| `timestamp` | TEXT | ISO 8601 метка времени |
| `segment_id` | TEXT FK | Ссылка на segments.id |
| `current_speed_kmh` | INTEGER | Текущая скорость |
| `free_flow_speed_kmh` | INTEGER | Скорость свободного потока |
| `current_travel_time_seconds` | INTEGER | Текущее время проезда |
| `free_flow_travel_time_seconds` | INTEGER | Время свободного проезда |
| `confidence` | REAL | Достоверность данных (0–1) |
| `road_closure` | INTEGER | Перекрытие дороги (0/1) |
| `frc` | TEXT | Functional Road Class |
| `status` | TEXT | `OK` или `FAIL` |
| `error_message` | TEXT | Текст ошибки |
| `raw_response` | TEXT | JSON-ответ API |

### `snapshots`

| Колонка | Тип | Описание |
|---|---|---|
| `id` | INTEGER PK | Автоинкремент |
| `timestamp` | TEXT | ISO 8601 метка времени |
| `json_payload` | TEXT | Полный JSON-снимок |
| `text_payload` | TEXT | Текст для LLM |

## Архитектура

```
┌──────────┐     ┌─────────────────┐     ┌──────────┐
│ segments │────▶│  tomtom_client   │────▶│   API    │
│  .yaml   │     │  (httpx async)   │     │  TomTom  │
└──────────┘     └────────┬────────┘     └──────────┘
                          │
                          ▼
                   ┌──────────────┐     ┌──────────┐
                   │  congestion  │◀────│   БД     │
                   │  .py         │     │ SQLite   │
                   └──────┬───────┘     └──────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  formatter   │
                   │  JSON/LLM    │
                   └──────────────┘
```

1. `config_loader` загружает участки из YAML
2. `tomtom_client` отправляет параллельные запросы к TomTom Flow Segment Data API (семафор ограничивает до 5 одновременных)
3. Результаты сохраняются в `measurements` через `database`
4. `congestion` вычисляет уровень загруженности для каждого участка
5. `formatter` генерирует JSON-снимок и текст для LLM
6. Снимок сохраняется в `snapshots`

Ошибка одного участка не прерывает сбор остальных.

## Тесты и качество кода

```bash
pytest                          # все тесты (mock, без реальных запросов к API)
pytest --cov=src                # с coverage-отчётом
ruff check .                    # линтер
ruff format --check .           # проверка форматирования
mypy src                        # статическая типизация
```

## Структура проекта

```
.
├── config/
│   └── segments.yaml           # конфигурация контрольных участков
├── src/almaty_traffic/
│   ├── __init__.py             # версия пакета
│   ├── settings.py             # загрузка .env + маскировка ключа в логах
│   ├── models.py               # pydantic-модели (TrafficMeasurement, CongestionResult, ...)
│   ├── config_loader.py        # загрузка и валидация segments.yaml
│   ├── tomtom_client.py        # async httpx-клиент TomTom Flow Segment Data API
│   ├── database.py             # aiosqlite CRUD + автосоздание таблиц
│   ├── congestion.py           # классификация загруженности по congestion_ratio
│   ├── formatter.py            # форматирование: JSON и текст для LLM
│   ├── scheduler.py            # циклический сбор с обработкой SIGINT/SIGTERM
│   ├── calibrate.py            # калибровка базового времени по ночным измерениям
│   ├── utils.py                # now_almaty_iso()
│   └── cli.py                  # CLI на typer (6 команд)
├── tests/                      # тесты (pytest + pytest-asyncio)
├── .env.example                # шаблон переменных окружения
├── pyproject.toml              # метаданные, зависимости, ruff, mypy, pytest
└── README.md
```

## Лицензия

MIT
