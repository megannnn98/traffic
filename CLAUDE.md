# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Статус проекта

Проект находится в фазе плана: кода ещё нет. Единственный источник истины —
`IMPLEMENTATION_PLAN.md` (полное ТЗ, проверенные факты об API, архитектурные решения,
9 этапов с критериями проверки). Перед любой работой читай его; при противоречии между
этим файлом и планом — план главнее.

## Что это

CLI-сервис на Python 3.12+: опрос времени движения по контрольным участкам Алматы через
официальный Yandex Distance Matrix API, история в SQLite, генерация JSON-снимка и русского
текста для LLM. Только официальный API — парсинг Яндекс Карт запрещён.

## Зафиксированные решения (не пересматривать без запроса пользователя)

- Yandex Distance Matrix API возвращает только декартов продукт origins × destinations,
  поэтому: **один HTTP-запрос 1×1 на участок**, параллелизм через `asyncio.Semaphore(5)`.
- Время: внутри программы UTC-aware `datetime`; в SQLite и выводе — ISO 8601 в `Asia/Almaty`.
- Пороги классификации загруженности — именованные константы в `src/almaty_traffic/congestion.py`.
- Слои разделены: HTTP (`yandex_client.py`) / БД (`database.py`) / вычисления (`congestion.py`)
  / форматирование (`formatter.py`). Без глобального изменяемого состояния.
- Ошибка одного участка не прерывает цикл сбора; API-ключ (`YANDEX_API_KEY`) никогда
  не попадает в логи и в Git.

## Команды (после реализации этапа 1)

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"

pytest                                  # все тесты (mock, без реальных запросов к API)
pytest tests/test_congestion.py -k name # один тест
ruff check . && ruff format .           # линт и форматирование
mypy src                                # проверка типов

almaty-traffic validate-config          # проверка config/segments.yaml
almaty-traffic collect                  # один цикл сбора
almaty-traffic run --interval 300       # постоянный сборщик
almaty-traffic report --format llm      # текст для LLM
almaty-traffic calibrate --days 14      # калибровка базового времени
```

## Порядок работы

- Этапы 1–9 из `IMPLEMENTATION_PLAN.md` выполнять строго последовательно; после каждого —
  прогон тестов и краткий отчёт.
- Тесты не ходят в реальный API — только `httpx.MockTransport`. Целевое покрытие ≥85%.
- Критерии готовности и запреты первого релиза (без веб-интерфейса, Docker, PostgreSQL,
  Telegram-бота и т.п.) — разделы 19–20 плана.
