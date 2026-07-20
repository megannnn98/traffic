import json
from pathlib import Path

import pytest

from almaty_traffic.database import Database
from almaty_traffic.models import MeasurementStatus, RouteMeasurement


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.sqlite3")
    await database.initialize()
    return database


def _measurement(
    segment_id: str = "seg1",
    status: MeasurementStatus = MeasurementStatus.OK,
    duration: int = 600,
) -> RouteMeasurement:
    from almaty_traffic.utils import now_almaty_iso

    return RouteMeasurement(
        timestamp=now_almaty_iso(),
        segment_id=segment_id,
        distance_meters=3100,
        duration_seconds=duration,
        status=status,
        raw_response={"status": "OK", "duration": {"value": duration}},
    )


class TestDatabaseInit:
    @pytest.mark.asyncio
    async def test_tables_created(self, db: Database) -> None:
        async with db._conn() as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row[0] for row in await cursor.fetchall()}
        assert "segments" in tables
        assert "measurements" in tables
        assert "snapshots" in tables

    @pytest.mark.asyncio
    async def test_idempotent_init(self, tmp_path: Path) -> None:
        db1 = Database(tmp_path / "test.sqlite3")
        await db1.initialize()
        db2 = Database(tmp_path / "test.sqlite3")
        await db2.initialize()
        async with db2._conn() as conn:
            cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            rows = await cursor.fetchall()
        assert len(rows) >= 3


class TestMeasurements:
    @pytest.mark.asyncio
    async def test_insert_and_read(self, db: Database) -> None:
        m = _measurement()
        await db.insert_measurement(m)
        rows = await db.get_measurements("seg1", hours=1)
        assert len(rows) == 1
        assert rows[0].segment_id == "seg1"
        assert rows[0].duration_seconds == 600

    @pytest.mark.asyncio
    async def test_multiple_measurements(self, db: Database) -> None:
        for i in range(3):
            m = _measurement(duration=600 + i * 100)
            await db.insert_measurement(m)
        rows = await db.get_measurements("seg1", hours=1)
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_get_measurements_empty(self, db: Database) -> None:
        rows = await db.get_measurements("nonexistent", hours=24)
        assert rows == []


class TestSnapshots:
    @pytest.mark.asyncio
    async def test_insert_and_read_snapshot(self, db: Database) -> None:
        payload = {"timestamp": "2026-07-20T10:00:00+05:00", "segments": []}
        text = "Свободное движение."
        await db.insert_snapshot(json.dumps(payload, ensure_ascii=False), text)
        snapshot = await db.get_latest_snapshot()
        assert snapshot is not None
        assert snapshot["json_payload"] == json.dumps(payload, ensure_ascii=False)
        assert snapshot["text_payload"] == text

    @pytest.mark.asyncio
    async def test_get_latest_snapshot_empty(self, db: Database) -> None:
        snapshot = await db.get_latest_snapshot()
        assert snapshot is None

    @pytest.mark.asyncio
    async def test_insert_snapshot_with_segments(self, db: Database) -> None:
        payload = {
            "timestamp": "2026-07-20T10:00:00+05:00",
            "segments": [
                {
                    "id": "seg1",
                    "road": "проспект",
                    "duration_seconds": 600,
                    "congestion_level": "dense",
                }
            ],
            "summary": {"total_segments": 1, "successful_segments": 1, "failed_segments": 0},
        }
        await db.insert_snapshot(json.dumps(payload), "Текст")
        snapshot = await db.get_latest_snapshot()
        assert snapshot is not None
        data = json.loads(snapshot["json_payload"])
        assert len(data["segments"]) == 1
