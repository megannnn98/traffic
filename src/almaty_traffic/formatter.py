import json
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from almaty_traffic.models import CongestionLevel, CongestionResult, SnapshotSummary

_LEVEL_ORDER = {
    CongestionLevel.SEVERE_TRAFFIC_JAM: 0,
    CongestionLevel.TRAFFIC_JAM: 1,
    CongestionLevel.DENSE: 2,
    CongestionLevel.LIGHT: 3,
    CongestionLevel.FREE: 4,
    CongestionLevel.UNKNOWN: 5,
}

_LEVEL_NAMES = {
    CongestionLevel.SEVERE_TRAFFIC_JAM: "Сильные пробки",
    CongestionLevel.TRAFFIC_JAM: "Пробки",
    CongestionLevel.DENSE: "Плотное движение",
    CongestionLevel.LIGHT: "Небольшое замедление",
    CongestionLevel.FREE: "Свободное движение",
}

_LEVEL_NAMES_LLM = {
    CongestionLevel.SEVERE_TRAFFIC_JAM: "Сильные пробки",
    CongestionLevel.TRAFFIC_JAM: "Пробки",
    CongestionLevel.DENSE: "Плотное движение",
    CongestionLevel.LIGHT: "Небольшое замедление",
    CongestionLevel.FREE: "Свободное движение",
}


def format_minutes(n: int) -> str:
    """Склонение минут: 1 минута, 2 минуты, 5 минут, 21 минута, ..."""
    if 11 <= n % 100 <= 19:
        return f"{n} минут"
    last = n % 10
    if last == 1:
        return f"{n} минута"
    if 2 <= last <= 4:
        return f"{n} минуты"
    return f"{n} минут"


def _sort_results(results: list[CongestionResult]) -> list[CongestionResult]:
    return sorted(results, key=lambda r: (_LEVEL_ORDER[r.congestion_level], -r.delay_seconds))


def _now_almaty() -> datetime:
    return datetime.now(ZoneInfo("Asia/Almaty"))


def format_snapshot_json(results: list[CongestionResult], summary: SnapshotSummary) -> str:
    """JSON-снимок обстановки."""
    sorted_results = _sort_results(results)
    now = _now_almaty()

    segments = []
    for r in sorted_results:
        segments.append(
            {
                "id": r.segment_id,
                "duration_seconds": r.duration_seconds,
                "free_flow_duration_seconds": r.free_flow_duration_seconds,
                "delay_seconds": r.delay_seconds,
                "congestion_ratio": (
                    round(r.congestion_ratio, 2) if r.congestion_ratio is not None else None
                ),
                "congestion_level": r.congestion_level.value,
            }
        )

    snapshot = {
        "timestamp": now.isoformat(),
        "city": "Алматы",
        "source": "Yandex Distance Matrix API",
        "segments": segments,
        "summary": {
            "total_segments": summary.total_segments,
            "successful_segments": summary.successful_segments,
            "failed_segments": summary.failed_segments,
            "traffic_jam_segments": summary.traffic_jam_segments,
            "severe_traffic_jam_segments": summary.severe_traffic_jam_segments,
        },
    }
    return json.dumps(snapshot, ensure_ascii=False, indent=2)


def _format_duration_line(r: CongestionResult) -> str:
    """Одна строка описания участка."""
    if r.duration_seconds is None:
        return "— Нет данных о времени."

    duration_min = r.duration_seconds // 60
    free_min = r.free_flow_duration_seconds // 60
    delay_min = r.delay_seconds // 60

    parts = [f"Поездка занимает {format_minutes(duration_min)}"]
    if free_min > 0:
        parts[0] += f" вместо обычных {format_minutes(free_min)}"
    parts[0] += "."
    if delay_min > 0:
        parts.append(f"Задержка около {format_minutes(delay_min)}.")
    return " ".join(parts)


def format_snapshot_llm(
    results: list[CongestionResult],
    summary: SnapshotSummary,
    only_congested: bool = False,
) -> str:
    """Русский текст для LLM."""
    now = _now_almaty()
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M")
    lines = [f"Дорожная обстановка в Алматы на {date_str} года, {time_str}.\n"]

    sorted_results = _sort_results(results)

    if only_congested:
        sorted_results = [r for r in sorted_results if r.congestion_level != CongestionLevel.FREE]

    grouped: dict[CongestionLevel, list[CongestionResult]] = defaultdict(list)
    for r in sorted_results:
        grouped[r.congestion_level].append(r)

    for level in (
        CongestionLevel.SEVERE_TRAFFIC_JAM,
        CongestionLevel.TRAFFIC_JAM,
        CongestionLevel.DENSE,
        CongestionLevel.LIGHT,
        CongestionLevel.FREE,
    ):
        segs = grouped.get(level, [])
        if not segs:
            continue
        lines.append(f"{_LEVEL_NAMES[level]}:")
        for r in segs:
            lines.append(f"— {r.segment_id}. {_format_duration_line(r)}")
        lines.append("")

    if summary.failed_segments > 0:
        word = "участка" if summary.failed_segments == 1 else "участков"
        lines.append(f"Не удалось получить данные для {summary.failed_segments} {word}.")

    return "\n".join(lines)


def format_snapshot_machine(results: list[CongestionResult], summary: SnapshotSummary) -> str:
    """Машинный формат key=value."""
    now = _now_almaty()
    lines = [
        f"timestamp={now.isoformat()}",
        "city=Алматы",
    ]

    for r in _sort_results(results):
        lines.append(f"segment={r.segment_id}")
        if r.duration_seconds is not None:
            lines.append(f"duration_min={r.duration_seconds // 60}")
        if r.free_flow_duration_seconds > 0:
            lines.append(f"baseline_min={r.free_flow_duration_seconds // 60}")
        lines.append(f"delay_min={r.delay_seconds // 60}")
        lines.append(f"congestion_level={r.congestion_level.value}")
        lines.append("")

    return "\n".join(lines)
