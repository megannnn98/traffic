# almaty-traffic

CLI-сервис сбора и текстового описания пробок Алматы через официальный Yandex Distance Matrix API.

**Важно**: Это **не** официальный балл пробок Яндекса. Сервис использует Yandex Distance Matrix API для получения времени движения по контрольным участкам и рассчитывает загруженность относительно базового времени свободного движения.

## Ограничения

- Только официальный Yandex Distance Matrix API (парсинг Яндекс Карт запрещён).
- Базовое время определяется по ночным измерениям (02:00–05:00).
- Нет прогнозирования — только текущее состояние.

## Получение API-ключа

1. Зарегистрируйтесь в [кабинете разработчика Yandex Maps API](https://developer.tech.yandex.ru/).
2. Создайте проект и получите API-ключ.
3. Добавьте в `.env`:
   ```
   YANDEX_API_KEY=ваш_ключ
   ```

## Установка (Arch Linux)

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Настройка

Скопируйте `.env.example` в `.env` и заполните:

```bash
cp .env.example .env
# Отредактируйте .env, добавьте YANDEX_API_KEY
```

Конфигурация участков — `config/segments.yaml`. Координаты демонстрационные, проверьте в Яндекс Картах.

## Запуск

```bash
# Проверка конфигурации
almaty-traffic validate-config

# Один цикл сбора
almaty-traffic collect

# Постоянный сбор (каждые 300 сек)
almaty-traffic run --interval 300

# Отчёт (последний снимок)
almaty-traffic report --format llm
almaty-traffic report --format json

# История участка
almaty-traffic history abai_nazarbayev_seifullin_east --hours 24

# Калибровка базового времени
almaty-traffic calibrate --days 14
almaty-traffic calibrate --days 14 --write-config
```

## Пример JSON-снимка

```json
{
  "timestamp": "2026-07-20T10:15:00+05:00",
  "city": "Алматы",
  "source": "Yandex Distance Matrix API",
  "segments": [
    {
      "id": "abai_nazarbayev_seifullin_east",
      "duration_seconds": 720,
      "free_flow_duration_seconds": 240,
      "delay_seconds": 480,
      "congestion_ratio": 3.0,
      "congestion_level": "severe_traffic_jam"
    }
  ],
  "summary": {
    "total_segments": 1,
    "successful_segments": 1,
    "failed_segments": 0,
    "traffic_jam_segments": 0,
    "severe_traffic_jam_segments": 1
  }
}
```

## Пример текста для LLM

```
Дорожная обстановка в Алматы на 20.07.2026 года, 10:15.

Сильные пробки:
— seg1. Поездка занимает 12 минут вместо обычных 4 минут. Задержка около 8 минут.
```

## Схема БД

- `segments` — контрольные участки
- `measurements` — измерения времени движения
- `snapshots` — JSON-снимки обстановки

## Тесты и качество кода

```bash
pytest                          # все тесты (73, mock без реальных запросов к API)
pytest --cov=src                # покрытие кода
ruff check .                    # линтер
ruff format --check .           # форматирование
mypy src                        # проверка типов
```

Целевое покрытие: ≥85% (фактически: 87%).

## Структура

```
src/almaty_traffic/
├── __init__.py          # версия
├── settings.py          # настройки из .env
├── models.py            # pydantic-модели
├── config_loader.py     # загрузка YAML
├── yandex_client.py     # async клиент API
├── database.py          # aiosqlite CRUD
├── congestion.py        # формулы загруженности
├── formatter.py         # JSON/LLM/text форматирование
├── collector.py         # сбор данных
├── scheduler.py         # циклический сбор
├── calibrate.py         # калибровка базового времени
└── cli.py               # CLI entry point
```
