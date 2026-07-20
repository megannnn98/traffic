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
    CongestionLevel.UNKNOWN: "Нет данных о загруженности",
}


def _sort_results(results: list[CongestionResult]) -> list[CongestionResult]:
    return sorted(
        results,
        key=lambda r: (_LEVEL_ORDER[r.congestion_level], -(r.congestion_ratio or 0)),
    )


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
                "current_speed_kmh": r.current_speed_kmh,
                "free_flow_speed_kmh": r.free_flow_speed_kmh,
                "current_travel_time_seconds": r.current_travel_time_seconds,
                "free_flow_travel_time_seconds": r.free_flow_travel_time_seconds,
                "confidence": r.confidence,
                "road_closure": r.road_closure,
                "congestion_ratio": (
                    round(r.congestion_ratio, 2) if r.congestion_ratio is not None else None
                ),
                "congestion_level": r.congestion_level.value,
            }
        )

    snapshot = {
        "timestamp": now.isoformat(),
        "city": "Алматы",
        "source": "TomTom Flow Segment Data API",
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


def _format_segment_line(r: CongestionResult) -> str:
    """Одна строка описания участка."""
    if r.road_closure:
        return "Дорога перекрыта."

    if r.current_speed_kmh is None or r.free_flow_speed_kmh is None:
        return "Нет данных о скорости."

    speed_drop_pct = 0
    if r.free_flow_speed_kmh > 0:
        speed_drop_pct = int((1 - r.current_speed_kmh / r.free_flow_speed_kmh) * 100)

    lines = [
        f"Текущая скорость: {r.current_speed_kmh} км/ч.",
        f"Обычная скорость: {r.free_flow_speed_kmh} км/ч.",
        f"Снижение скорости: {speed_drop_pct}%.",
    ]

    if r.current_travel_time_seconds and r.free_flow_travel_time_seconds:
        current_min = r.current_travel_time_seconds // 60
        free_min = r.free_flow_travel_time_seconds // 60
        lines.append(f"Поездка: {current_min} мин вместо {free_min} мин.")

    return " ".join(lines)


def format_snapshot_llm(
    results: list[CongestionResult],
    summary: SnapshotSummary,
    only_congested: bool = False,
    timestamp: datetime | None = None,
) -> str:
    """Русский текст для LLM."""
    now = timestamp or _now_almaty()
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M")
    lines = [f"Дорожная обстановка в Алматы на {date_str} года, {time_str}.\n"]

    sorted_results = _sort_results(results)

    if only_congested:
        sorted_results = [
            r
            for r in sorted_results
            if r.congestion_level not in (CongestionLevel.FREE, CongestionLevel.UNKNOWN)
        ]

    grouped: dict[CongestionLevel, list[CongestionResult]] = defaultdict(list)
    for r in sorted_results:
        grouped[r.congestion_level].append(r)

    for level in (
        CongestionLevel.SEVERE_TRAFFIC_JAM,
        CongestionLevel.TRAFFIC_JAM,
        CongestionLevel.DENSE,
        CongestionLevel.LIGHT,
        CongestionLevel.FREE,
        CongestionLevel.UNKNOWN,
    ):
        segs = grouped.get(level, [])
        if not segs:
            continue
        lines.append(f"{_LEVEL_NAMES[level]}:")
        for r in segs:
            lines.append(f"— {r.segment_id}. {_format_segment_line(r)}")
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
        if r.road_closure:
            lines.append("road_closure=true")
        if r.current_speed_kmh is not None:
            lines.append(f"current_speed={r.current_speed_kmh}")
        if r.free_flow_speed_kmh is not None:
            lines.append(f"free_flow_speed={r.free_flow_speed_kmh}")
        if r.current_travel_time_seconds is not None:
            lines.append(f"travel_time={r.current_travel_time_seconds}")
        if r.free_flow_travel_time_seconds is not None:
            lines.append(f"free_flow_travel_time={r.free_flow_travel_time_seconds}")
        if r.confidence is not None:
            lines.append(f"confidence={r.confidence}")
        lines.append(f"congestion_level={r.congestion_level.value}")
        lines.append("")

    return "\n".join(lines)
