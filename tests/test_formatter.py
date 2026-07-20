import json

from almaty_traffic.formatter import (
    format_minutes,
    format_snapshot_json,
    format_snapshot_llm,
    format_snapshot_machine,
)
from almaty_traffic.models import CongestionLevel, CongestionResult, SnapshotSummary


def _congestion(
    segment_id: str = "seg1",
    duration: int = 600,
    free_flow: int = 240,
    level: CongestionLevel = CongestionLevel.TRAFFIC_JAM,
) -> CongestionResult:
    return CongestionResult(
        segment_id=segment_id,
        duration_seconds=duration,
        free_flow_duration_seconds=free_flow,
        delay_seconds=duration - free_flow,
        congestion_ratio=duration / free_flow if free_flow > 0 else None,
        congestion_level=level,
    )


class TestFormatMinutes:
    def test_one(self) -> None:
        assert format_minutes(1) == "1 минута"

    def test_two(self) -> None:
        assert format_minutes(2) == "2 минуты"

    def test_four(self) -> None:
        assert format_minutes(4) == "4 минуты"

    def test_five(self) -> None:
        assert format_minutes(5) == "5 минут"

    def test_eleven(self) -> None:
        assert format_minutes(11) == "11 минут"

    def test_fourteen(self) -> None:
        assert format_minutes(14) == "14 минут"

    def test_twenty_one(self) -> None:
        assert format_minutes(21) == "21 минута"

    def test_twenty_five(self) -> None:
        assert format_minutes(25) == "25 минут"

    def test_zero(self) -> None:
        assert format_minutes(0) == "0 минут"

    def test_hundred_one(self) -> None:
        assert format_minutes(101) == "101 минута"


class TestFormatSnapshotJson:
    def test_structure(self) -> None:
        results = [_congestion()]
        summary = SnapshotSummary(
            total_segments=1,
            successful_segments=1,
            failed_segments=0,
            traffic_jam_segments=1,
            severe_traffic_jam_segments=0,
        )
        snap = format_snapshot_json(results, summary)
        data = json.loads(snap)
        assert data["city"] == "Алматы"
        assert data["source"] == "Yandex Distance Matrix API"
        assert len(data["segments"]) == 1
        assert data["summary"]["total_segments"] == 1

    def test_sorting(self) -> None:
        results = [
            _congestion("free_seg", level=CongestionLevel.FREE),
            _congestion("jam_seg", level=CongestionLevel.TRAFFIC_JAM),
            _congestion("severe_seg", level=CongestionLevel.SEVERE_TRAFFIC_JAM),
        ]
        summary = SnapshotSummary(
            total_segments=3,
            successful_segments=3,
            failed_segments=0,
            traffic_jam_segments=1,
            severe_traffic_jam_segments=1,
        )
        snap = format_snapshot_json(results, summary)
        data = json.loads(snap)
        levels = [s["congestion_level"] for s in data["segments"]]
        assert levels[0] == "severe_traffic_jam"
        assert levels[-1] == "free"


class TestFormatSnapshotLlm:
    def test_contains_city(self) -> None:
        results = [_congestion()]
        summary = SnapshotSummary(
            total_segments=1,
            successful_segments=1,
            failed_segments=0,
            traffic_jam_segments=1,
        )
        text = format_snapshot_llm(results, summary)
        assert "Алматы" in text

    def test_groups_by_level(self) -> None:
        results = [
            _congestion("jam", level=CongestionLevel.TRAFFIC_JAM),
            _congestion("free", level=CongestionLevel.FREE),
        ]
        summary = SnapshotSummary(total_segments=2, successful_segments=2, failed_segments=0)
        text = format_snapshot_llm(results, summary)
        assert "Пробки" in text or "пробки" in text.lower()
        assert "Свободное" in text or "свободное" in text.lower()

    def test_only_congested(self) -> None:
        results = [
            _congestion("jam", level=CongestionLevel.TRAFFIC_JAM),
            _congestion("free", level=CongestionLevel.FREE),
        ]
        summary = SnapshotSummary(total_segments=2, successful_segments=2, failed_segments=0)
        text = format_snapshot_llm(results, summary, only_congested=True)
        assert "free" not in text.lower() or "Свободное" not in text

    def test_failed_segments(self) -> None:
        results = [_congestion()]
        summary = SnapshotSummary(
            total_segments=2,
            successful_segments=1,
            failed_segments=1,
        )
        text = format_snapshot_llm(results, summary)
        assert "1" in text and ("ошибк" in text.lower() or "не удалось" in text.lower())


class TestFormatSnapshotMachine:
    def test_key_value(self) -> None:
        results = [_congestion()]
        summary = SnapshotSummary(total_segments=1, successful_segments=1, failed_segments=0)
        text = format_snapshot_machine(results, summary)
        lines = text.strip().split("\n")
        assert any("timestamp=" in line for line in lines)
        assert any("segment=" in line for line in lines)
        assert any("congestion_level=" in line for line in lines)
