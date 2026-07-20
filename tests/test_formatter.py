import json

from almaty_traffic.formatter import (
    format_snapshot_json,
    format_snapshot_llm,
    format_snapshot_machine,
)
from almaty_traffic.models import CongestionLevel, CongestionResult, SnapshotSummary


def _congestion(
    segment_id: str = "seg1",
    current_speed: int = 41,
    free_flow_speed: int = 70,
    current_travel_time: int = 153,
    free_flow_travel_time: int = 90,
    level: CongestionLevel = CongestionLevel.DENSE,
    road_closure: bool = False,
) -> CongestionResult:
    return CongestionResult(
        segment_id=segment_id,
        current_speed_kmh=current_speed,
        free_flow_speed_kmh=free_flow_speed,
        current_travel_time_seconds=current_travel_time,
        free_flow_travel_time_seconds=free_flow_travel_time,
        confidence=0.59,
        road_closure=road_closure,
        congestion_ratio=current_travel_time / free_flow_travel_time
        if free_flow_travel_time > 0
        else None,
        congestion_level=level,
    )


class TestFormatSnapshotJson:
    def test_structure(self) -> None:
        results = [_congestion()]
        summary = SnapshotSummary(
            total_segments=1,
            successful_segments=1,
            failed_segments=0,
        )
        snap = format_snapshot_json(results, summary)
        data = json.loads(snap)
        assert data["city"] == "Алматы"
        assert data["source"] == "TomTom Flow Segment Data API"
        assert len(data["segments"]) == 1
        assert data["segments"][0]["current_speed_kmh"] == 41
        assert data["segments"][0]["free_flow_speed_kmh"] == 70
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
        )
        snap = format_snapshot_json(results, summary)
        data = json.loads(snap)
        levels = [s["congestion_level"] for s in data["segments"]]
        assert levels[0] == "severe_traffic_jam"
        assert levels[-1] == "free"


class TestFormatSnapshotLlm:
    def test_contains_city(self) -> None:
        results = [_congestion()]
        summary = SnapshotSummary(total_segments=1, successful_segments=1, failed_segments=0)
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

    def test_road_closure(self) -> None:
        results = [_congestion("closed", road_closure=True)]
        summary = SnapshotSummary(total_segments=1, successful_segments=1, failed_segments=0)
        text = format_snapshot_llm(results, summary)
        assert "перекрыта" in text.lower()

    def test_speed_info(self) -> None:
        results = [_congestion()]
        summary = SnapshotSummary(total_segments=1, successful_segments=1, failed_segments=0)
        text = format_snapshot_llm(results, summary)
        assert "41 км/ч" in text
        assert "70 км/ч" in text

    def test_failed_segments(self) -> None:
        results = [_congestion()]
        summary = SnapshotSummary(
            total_segments=2,
            successful_segments=1,
            failed_segments=1,
        )
        text = format_snapshot_llm(results, summary)
        assert "1" in text and ("ошибк" in text.lower() or "не удалось" in text.lower())

    def test_unknown_level_not_silently_dropped(self) -> None:
        results = [
            _congestion("jam", level=CongestionLevel.TRAFFIC_JAM),
            _congestion(
                "no_baseline",
                level=CongestionLevel.UNKNOWN,
                free_flow_travel_time=0,
            ),
        ]
        summary = SnapshotSummary(total_segments=2, successful_segments=2, failed_segments=0)
        text = format_snapshot_llm(results, summary)
        assert "no_baseline" in text

    def test_only_congested_excludes_unknown(self) -> None:
        results = [
            _congestion("jam", level=CongestionLevel.TRAFFIC_JAM),
            _congestion(
                "no_baseline",
                level=CongestionLevel.UNKNOWN,
                free_flow_travel_time=0,
            ),
        ]
        summary = SnapshotSummary(total_segments=2, successful_segments=2, failed_segments=0)
        text = format_snapshot_llm(results, summary, only_congested=True)
        assert "no_baseline" not in text
        assert "jam" in text


class TestFormatSnapshotMachine:
    def test_key_value(self) -> None:
        results = [_congestion()]
        summary = SnapshotSummary(total_segments=1, successful_segments=1, failed_segments=0)
        text = format_snapshot_machine(results, summary)
        lines = text.strip().split("\n")
        assert any("timestamp=" in line for line in lines)
        assert any("segment=" in line for line in lines)
        assert any("current_speed=" in line for line in lines)
        assert any("free_flow_speed=" in line for line in lines)
        assert any("congestion_level=" in line for line in lines)

    def test_road_closure_in_machine_format(self) -> None:
        results = [_congestion("closed", road_closure=True)]
        summary = SnapshotSummary(total_segments=1, successful_segments=1, failed_segments=0)
        text = format_snapshot_machine(results, summary)
        assert "road_closure=true" in text

    def test_confidence_in_machine_format(self) -> None:
        results = [_congestion()]
        summary = SnapshotSummary(total_segments=1, successful_segments=1, failed_segments=0)
        text = format_snapshot_machine(results, summary)
        assert "confidence=0.59" in text
