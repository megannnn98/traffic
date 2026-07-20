import json
from pathlib import Path

import pytest

from almaty_traffic.database import Database
from almaty_traffic.models import MeasurementStatus, TrafficMeasurement


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.sqlite3")
    await database.initialize()
    return database


def _measurement(
    segment_id: str = "seg1",
    status: MeasurementStatus = MeasurementStatus.OK,
    current_speed: int = 41,
    free_flow_speed: int = 70,
) -> TrafficMeasurement:
    from almaty_traffic.utils import now_almaty_iso

    return TrafficMeasurement(
        timestamp=now_almaty_iso(),
        segment_id=segment_id,
        current_speed_kmh=current_speed,
        free_flow_speed_kmh=free_flow_speed,
        current_travel_time_seconds=153,
        free_flow_travel_time_seconds=90,
        confidence=0.59,
        road_closure=False,
        frc="FRC2",
        status=status,
        raw_response={"currentSpeed": current_speed, "freeFlowSpeed": free_flow_speed},
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
        assert rows[0].current_speed_kmh == 41
        assert rows[0].free_flow_speed_kmh == 70

    @pytest.mark.asyncio
    async def test_multiple_measurements(self, db: Database) -> None:
        for i in range(3):
            m = _measurement(current_speed=40 + i * 5)
            await db.insert_measurement(m)
        rows = await db.get_measurements("seg1", hours=1)
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_get_measurements_empty(self, db: Database) -> None:
        rows = await db.get_measurements("nonexistent", hours=24)
        assert rows == []

    @pytest.mark.asyncio
    async def test_road_closure(self, db: Database) -> None:
        m = _measurement()
        m.road_closure = True
        m.current_speed_kmh = 0
        await db.insert_measurement(m)
        rows = await db.get_measurements("seg1", hours=1)
        assert len(rows) == 1
        assert rows[0].road_closure is True
        assert rows[0].current_speed_kmh == 0


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
