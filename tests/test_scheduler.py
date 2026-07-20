import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml

from almaty_traffic.models import MeasurementStatus, TrafficMeasurement
from almaty_traffic.scheduler import _collect_cycle


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


def test_collect_cycle(tmp_path: Path) -> None:
    segments_path = tmp_path / "segments.yaml"
    _write_segments(segments_path)
    db_path = tmp_path / "test.sqlite3"

    measurement = TrafficMeasurement(
        timestamp="2026-07-20T10:00:00+05:00",
        segment_id="seg1",
        current_speed_kmh=41,
        free_flow_speed_kmh=70,
        current_travel_time_seconds=153,
        free_flow_travel_time_seconds=90,
        confidence=0.59,
        road_closure=False,
        frc="FRC2",
        status=MeasurementStatus.OK,
    )

    mock_client = AsyncMock()
    mock_client.get_segments.return_value = [measurement]

    from almaty_traffic.settings import Settings

    settings = Settings(
        tomtom_api_key="test_key",
        database_path=db_path,
        segments_config=segments_path,
        request_timeout_seconds=15,
    )

    with (
        patch("almaty_traffic.tomtom_client.TomTomTrafficClient", return_value=mock_client),
        patch("almaty_traffic.scheduler.Database") as mock_db_cls,
    ):
        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db
        asyncio.run(_collect_cycle(settings))

    assert mock_db.insert_measurement.called
    assert mock_db.insert_snapshot.called
