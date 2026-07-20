# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Статус проекта

Проект реализован. Использует TomTom Flow Segment Data API для получения данных о пробках.

## Что это

CLI-сервис на Python 3.12+: опрос скорости и времени движения по контрольным участкам Алматы через
TomTom Flow Segment Data API, история в SQLite, генерация JSON-снимка и русского
текста для LLM.

## Архитектура

- `tomtom_client.py` — async клиент TomTom API (один запрос на точку)
- `database.py` — aiosqlite CRUD
- `congestion.py` — формулы загруженности (congestion_ratio = current_travel_time / free_flow_travel_time)
- `formatter.py` — JSON/LLM/text форматирование
- `scheduler.py` — циклический сбор с обработкой SIGINT/SIGTERM
- Пороги классификации загруженности — именованные константы в `congestion.py`.
- Ошибка одного участка не прерывает цикл сбора; API-ключ (`TOMTOM_API_KEY`) никогда
  не попадает в логи и в Git.

## Команды

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"

pytest                                  # все тесты (mock, без реальных запросов к API)
ruff check . && ruff format .           # линт и форматирование
mypy src                                # проверка типов

almaty-traffic validate-config          # проверка config/segments.yaml
almaty-traffic collect                  # один цикл сбора
almaty-traffic run --interval 300       # постоянный сборщик
almaty-traffic report --format llm      # текст для LLM
almaty-traffic calibrate --days 14      # калибровка базового времени
```
