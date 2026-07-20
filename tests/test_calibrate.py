import asyncio
from pathlib import Path

import yaml

from almaty_traffic.calibrate import calibrate_free_flow
from almaty_traffic.database import Database
from almaty_traffic.models import MeasurementStatus, TrafficMeasurement
from almaty_traffic.settings import Settings


def _write_segments(path: Path) -> None:
    data = {
        "segments": [
            {
                "id": "seg1",
                "road": "проспект",
                "direction": "восток",
                "from_name": "А",
                "to_name": "Б",
                "origin": {"latitude": 43.0, "longitude": 76.0},
                "destination": {"latitude": 43.1, "longitude": 76.1},
                "free_flow_duration_seconds": 240,
                "enabled": True,
            }
        ]
    }
    path.write_text(yaml.dump(data, allow_unicode=True))


async def _populate_night_measurements(db_path: Path, segments_path: Path) -> None:
    db = Database(db_path)
    await db.initialize()

    # 10 ночных замеров (03:00 Almaty)
    for i in range(10):
        m = TrafficMeasurement(
            timestamp=f"2026-07-1{i}T03:00:00+05:00",
            segment_id="seg1",
            current_speed_kmh=40 + i * 2,
            free_flow_speed_kmh=70,
            current_travel_time_seconds=200 + i * 10,  # 200, 210, ... 290
            free_flow_travel_time_seconds=90,
            confidence=0.8,
            road_closure=False,
            frc="FRC2",
            status=MeasurementStatus.OK,
        )
        await db.insert_measurement(m)


def test_calibrate_free_flow(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    segments_path = tmp_path / "segments.yaml"
    _write_segments(segments_path)
    asyncio.run(_populate_night_measurements(db_path, segments_path))

    settings = Settings(
        tomtom_api_key="test_key",
        database_path=db_path,
        segments_config=segments_path,
        request_timeout_seconds=15,
    )

    results = asyncio.run(calibrate_free_flow(settings, days=30))
    assert "seg1" in results
    # 20-й перцентиль из [200,210,...,290] → индекс 2 → 220
    assert results["seg1"] == 220


def test_calibrate_no_measurements(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.sqlite3"
    segments_path = tmp_path / "segments.yaml"
    _write_segments(segments_path)
    asyncio.run(Database(db_path).initialize())

    settings = Settings(
        tomtom_api_key="test_key",
        database_path=db_path,
        segments_config=segments_path,
        request_timeout_seconds=15,
    )

    results = asyncio.run(calibrate_free_flow(settings, days=14))
    # Без измерений — берём значение из конфига
    assert results.get("seg1") == 240
