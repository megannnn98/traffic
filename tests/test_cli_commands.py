import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml
from typer.testing import CliRunner

from almaty_traffic.cli import app
from almaty_traffic.database import Database
from almaty_traffic.models import MeasurementStatus, TrafficMeasurement

runner = CliRunner()


def _write_segments(path: Path) -> None:
    data = {
        "segments": [
            {
                "id": "seg1",
                "road": "проспект Абая",
                "direction": "восток",
                "from_name": "Назарбаева",
                "to_name": "Сейфуллина",
                "origin": {"latitude": 43.2381, "longitude": 76.9452},
                "destination": {"latitude": 43.2384, "longitude": 76.9281},
                "free_flow_duration_seconds": 240,
                "enabled": True,
            }
        ]
    }
    path.write_text(yaml.dump(data, allow_unicode=True))


async def _populate_db(db_path: Path) -> None:
    db = Database(db_path)
    await db.initialize()
    m = TrafficMeasurement(
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
    await db.insert_measurement(m)
    json_payload = json.dumps(
        {
            "timestamp": "2026-07-20T10:00:00+05:00",
            "segments": [
                {
                    "id": "seg1",
                    "current_speed_kmh": 41,
                    "free_flow_speed_kmh": 70,
                    "current_travel_time_seconds": 153,
                    "free_flow_travel_time_seconds": 90,
                    "confidence": 0.59,
                    "road_closure": False,
                    "congestion_ratio": 1.7,
                    "congestion_level": "dense",
                }
            ],
            "summary": {
                "total_segments": 1,
                "successful_segments": 1,
                "failed_segments": 0,
            },
        },
        ensure_ascii=False,
    )
    await db.insert_snapshot(json_payload, "Плотное движение на проспекте Абая.")


class TestReport:
    def test_report_llm(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.sqlite3"
        asyncio.run(_populate_db(db_path))

        with patch("almaty_traffic.cli.load_settings") as mock_s:
            mock_s.return_value.segments_config = tmp_path / "x.yaml"
            mock_s.return_value.database_path = db_path
            result = runner.invoke(app, ["report", "--format", "llm"])
        assert result.exit_code == 0
        assert "Абая" in result.output

    def test_report_json(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.sqlite3"
        asyncio.run(_populate_db(db_path))

        with patch("almaty_traffic.cli.load_settings") as mock_s:
            mock_s.return_value.segments_config = tmp_path / "x.yaml"
            mock_s.return_value.database_path = db_path
            result = runner.invoke(app, ["report", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["summary"]["total_segments"] == 1

    def test_report_no_data(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty.sqlite3"
        asyncio.run(Database(db_path).initialize())

        with patch("almaty_traffic.cli.load_settings") as mock_s:
            mock_s.return_value.segments_config = tmp_path / "x.yaml"
            mock_s.return_value.database_path = db_path
            result = runner.invoke(app, ["report"])
        assert result.exit_code == 0
        assert "нет данных" in result.output.lower() or "Нет" in result.output

    def test_report_only_congested(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.sqlite3"

        async def _populate() -> None:
            db = Database(db_path)
            await db.initialize()
            json_payload = json.dumps(
                {
                    "timestamp": "2026-07-20T10:00:00+05:00",
                    "segments": [
                        {
                            "id": "jam_seg",
                            "current_speed_kmh": 10,
                            "free_flow_speed_kmh": 50,
                            "current_travel_time_seconds": 300,
                            "free_flow_travel_time_seconds": 100,
                            "confidence": 0.8,
                            "road_closure": False,
                            "congestion_ratio": 3.0,
                            "congestion_level": "severe_traffic_jam",
                        },
                        {
                            "id": "free_seg",
                            "current_speed_kmh": 55,
                            "free_flow_speed_kmh": 60,
                            "current_travel_time_seconds": 100,
                            "free_flow_travel_time_seconds": 95,
                            "confidence": 0.9,
                            "road_closure": False,
                            "congestion_ratio": 1.05,
                            "congestion_level": "free",
                        },
                        {
                            "id": "unknown_seg",
                            "current_speed_kmh": None,
                            "free_flow_speed_kmh": None,
                            "current_travel_time_seconds": None,
                            "free_flow_travel_time_seconds": None,
                            "confidence": None,
                            "road_closure": False,
                            "congestion_ratio": None,
                            "congestion_level": "unknown",
                        },
                    ],
                    "summary": {
                        "total_segments": 3,
                        "successful_segments": 3,
                        "failed_segments": 0,
                        "traffic_jam_segments": 0,
                        "severe_traffic_jam_segments": 1,
                    },
                },
                ensure_ascii=False,
            )
            full_text = "jam_seg free_seg unknown_seg — все участки в полном тексте."
            await db.insert_snapshot(json_payload, full_text)

        asyncio.run(_populate())

        with patch("almaty_traffic.cli.load_settings") as mock_s:
            mock_s.return_value.segments_config = tmp_path / "x.yaml"
            mock_s.return_value.database_path = db_path
            result = runner.invoke(app, ["report", "--format", "llm", "--only-congested"])
        assert result.exit_code == 0
        assert "jam_seg" in result.output
        assert "free_seg" not in result.output
        assert "unknown_seg" not in result.output


class TestHistory:
    def test_history(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.sqlite3"
        asyncio.run(_populate_db(db_path))

        with patch("almaty_traffic.cli.load_settings") as mock_s:
            mock_s.return_value.segments_config = tmp_path / "x.yaml"
            mock_s.return_value.database_path = db_path
            result = runner.invoke(app, ["history", "seg1", "--hours", "24"])
        assert result.exit_code == 0
        assert "seg1" in result.output

    def test_history_empty(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty.sqlite3"
        asyncio.run(Database(db_path).initialize())

        with patch("almaty_traffic.cli.load_settings") as mock_s:
            mock_s.return_value.segments_config = tmp_path / "x.yaml"
            mock_s.return_value.database_path = db_path
            result = runner.invoke(app, ["history", "nonexistent"])
        assert result.exit_code == 0


class TestCollect:
    def test_collect_success(self, tmp_path: Path) -> None:
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

        with (
            patch("almaty_traffic.cli.load_settings") as mock_s,
            patch("almaty_traffic.cli.TomTomTrafficClient", return_value=mock_client),
            patch("almaty_traffic.cli.Database") as mock_db_cls,
        ):
            mock_s.return_value.segments_config = segments_path
            mock_s.return_value.database_path = db_path
            mock_s.return_value.tomtom_api_key = "test_key"
            mock_s.return_value.request_timeout_seconds = 15
            mock_db = AsyncMock()
            mock_db_cls.return_value = mock_db
            result = runner.invoke(app, ["collect"])
        assert result.exit_code == 0
        assert mock_db.insert_measurement.called

    def test_collect_missing_api_key(self, tmp_path: Path) -> None:
        segments_path = tmp_path / "segments.yaml"
        _write_segments(segments_path)
        db_path = tmp_path / "test.sqlite3"

        with patch("almaty_traffic.cli.load_settings") as mock_s:
            mock_s.return_value.segments_config = segments_path
            mock_s.return_value.database_path = db_path
            mock_s.return_value.tomtom_api_key = ""
            mock_s.return_value.request_timeout_seconds = 15
            result = runner.invoke(app, ["collect"])
        assert result.exit_code == 1
        assert "TOMTOM_API_KEY" in result.output
        assert "TRAFFIC_TOMTOM_API_KEY" not in result.output

    def test_collect_all_fail(self, tmp_path: Path) -> None:
        segments_path = tmp_path / "segments.yaml"
        _write_segments(segments_path)
        db_path = tmp_path / "test.sqlite3"

        measurement = TrafficMeasurement(
            timestamp="2026-07-20T10:00:00+05:00",
            segment_id="seg1",
            status=MeasurementStatus.FAIL,
            error_message="HTTP 403: Forbidden",
        )

        mock_client = AsyncMock()
        mock_client.get_segments.return_value = [measurement]

        with (
            patch("almaty_traffic.cli.load_settings") as mock_s,
            patch("almaty_traffic.cli.TomTomTrafficClient", return_value=mock_client),
            patch("almaty_traffic.cli.Database") as mock_db_cls,
        ):
            mock_s.return_value.segments_config = segments_path
            mock_s.return_value.database_path = db_path
            mock_s.return_value.tomtom_api_key = "test_key"
            mock_s.return_value.request_timeout_seconds = 15
            mock_db = AsyncMock()
            mock_db_cls.return_value = mock_db
            result = runner.invoke(app, ["collect"])
        assert result.exit_code == 1
        assert "Ошибок: 1" in result.output
